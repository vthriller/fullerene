#!/usr/bin/env python
from aiohttp import web, ClientSession
import asyncio
from time import time
from urllib.parse import quote
import json
import matplotlib.pyplot as plt
from io import BytesIO

async def handle(request):
	url = 'http://127.0.0.1:9090/api/v1/query_range?query={}&start={}&end={}&step={}'.format(
		quote('sum(rate(node_cpu{instance="localhost:9100"} [5m])) by (mode)'),
		time() - 3600,
		time(),
		5,
	)
	async with session.get(url) as response:
		data = await response.text()

		data = json.loads(data)
		if data['status'] != 'success':
			return web.Response('Bad gateway', 502)
		if data['data']['resultType'] != 'matrix':
			return web.Response('Bad gateway', 502)
		data = data['data']['result']

		fig, ax = plt.subplots()
		fig.tight_layout()
		ax.margins(0)

		for metric in data:
			ax.plot(
				[k for k, _ in metric['values']],
				[float(v) for _, v in metric['values']],
				label = str(metric['metric']),
			)

		ax.legend()

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
