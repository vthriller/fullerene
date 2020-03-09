#!/usr/bin/env python
from aiohttp import web, ClientSession
import asyncio
from time import time
from urllib.parse import quote
import json
from io import BytesIO

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime as dt

import matplotlib
matplotlib.rc('font', size=9)

async def handle(req):
	w = int(req.query.get('w', 800))
	h = int(req.query.get('h', 480))
	# and now, matplotlib quirks
	dpi = 100.
	w /= dpi
	h /= dpi

	now = time()
	end = int(req.query.get('end', now))
	start = int(req.query.get('start', end - 3600))

	url = 'http://127.0.0.1:9090/api/v1/query_range?query={}&start={}&end={}&step={}'.format(
		quote('sum(rate(node_cpu{instance="localhost:9100"} [5m])) by (mode)'),
		start, end, 5,
	)
	async with session.get(url) as response:
		data = await response.text()

		data = json.loads(data)
		if data['status'] != 'success':
			return web.Response('Bad gateway', 502)
		if data['data']['resultType'] != 'matrix':
			return web.Response('Bad gateway', 502)
		data = data['data']['result']

		fig = plt.figure(figsize=(w, h), dpi=dpi)
		ax = fig.add_subplot()
		fig.tight_layout(pad=0)
		ax.margins(0)

		ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d\n%H:%M'))

		for metric in data:
			ax.plot(
				[dt.fromtimestamp(k) for k, _ in metric['values']],
				[float(v) for _, v in metric['values']],
				label = str(metric['metric']),
			)

		ax.legend()
		ax.grid(True)

		# TODO? rotate dates
		# FIXME leftmost date occasionally gets clipped
		#fig.autofmt_xdate()

		buf = BytesIO()
		fig.savefig(buf, format='png')

		return web.Response(
			body = buf.getbuffer(),
			content_type = 'image/png',
		)

session = ClientSession()

app = web.Application()
app.add_routes([
	web.get('/', handle),
])

web.run_app(app, host='127.0.0.1', port=12345)
asyncio.get_event_loop().run_until_complete(
	session.close()
)
