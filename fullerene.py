#!/usr/bin/env python
from aiohttp import web, ClientSession
import asyncio
from time import time
from urllib.parse import quote
import json
from io import BytesIO
from collections import namedtuple
from string import Template

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime as dt

import matplotlib
matplotlib.rc('font', size=9)

Chart = namedtuple('Chart', ['queries', 'stacked'])
Query = namedtuple('Query', ['query', 'label'])

charts = dict(
	cpu = Chart(
		queries = [
			Query(
				query = 'sum(rate(node_cpu{instance="localhost:9100"} [5m])) by (mode)',
				label = '$mode',
			),
		],
		stacked = True,
	),
	mem = Chart(
		queries = [
			Query(
				query = 'node_memory_MemTotal{instance="localhost:9100"} - node_memory_MemFree{instance="localhost:9100"} - node_memory_Buffers{instance="localhost:9100"} - node_memory_Cached{instance="localhost:9100"}',
				label = 'used',
			),
			Query(
				query = 'node_memory_Shmem{instance="localhost:9100"}',
				label = 'shared + tmpfs',
			),
			Query(
				query = 'node_memory_Dirty{instance="localhost:9100"} + node_memory_Writeback{instance="localhost:9100"}',
				label = 'cached dirty',
			),
			Query(
				query = 'node_memory_Buffers{instance="localhost:9100"} + node_memory_Cached{instance="localhost:9100"} - node_memory_Shmem{instance="localhost:9100"} - node_memory_Dirty{instance="localhost:9100"} - node_memory_Writeback{instance="localhost:9100"}',
				label = 'cached clean',
			),
			Query(
				query = 'node_memory_MemFree{instance="localhost:9100"}',
				label = 'free',
			),
		],
		stacked = True,
	),
)

async def handle(req):
	chart = charts[req.match_info.get('chart')]

	w = int(req.query.get('w', 800))
	h = int(req.query.get('h', 480))
	# and now, matplotlib quirks
	dpi = 100.
	w /= dpi
	h /= dpi

	now = time()
	end = int(req.query.get('end', now))
	start = int(req.query.get('start', end - 3600))

	pitch = int((end-start) / w / dpi)

	fig = plt.figure(figsize=(w, h), dpi=dpi)
	ax = fig.add_subplot()
	# XXX disabled for a number of reasons:
	# - performance drop: https://github.com/matplotlib/matplotlib/issues/16550
	# - it doesn't play well with multiline formatters
	#fig.tight_layout(pad=0)
	ax.margins(0)

	ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d\n%H:%M'))

	metrics = []

	urls = [
		'http://127.0.0.1:9090/api/v1/query_range?query={}&start={}&end={}&step={}'.format(
			quote(q.query), start, end, pitch,
		) for q in chart.queries
	]
	templates = [Template(q.label) for q in chart.queries]
	for response, tmpl in zip(
		await asyncio.gather(*[
			session.get(url) for url in urls
		]),
		templates,
	):
		data = await response.text()

		data = json.loads(data)
		if data['status'] != 'success':
			return web.Response('Bad gateway', 502)
		if data['data']['resultType'] != 'matrix':
			return web.Response('Bad gateway', 502)
		data = data['data']['result']

		for metric in data:
			metric['metric'] = tmpl.safe_substitute(metric['metric'])

		metrics += data

	'''
	Fill the gaps in the data returned with NaN, so lines get split into multiple where data is missing.
	Prometheus seems to always return data keyed at range(start, end, step),
	skipping the keys that are missing from its backend.

	Grafana seems to do just that:
	https://github.com/grafana/grafana/blob/e68e93f595bd3d7265ee00e581c88c0391caccb4/public/app/plugins/datasource/prometheus/result_transformer.ts#L43
	'''

	NaN = float('nan')

	for metric in metrics:
		vals = dict(metric['values'])
		with_gaps = []
		for k in range(start, end, pitch):
			v = vals.get(k)
			if v is not None:
				v = float(v)
			else:
				v = NaN
			with_gaps.append(v)
		metric['values'] = with_gaps

	keys = [dt.fromtimestamp(k) for k in range(start, end, pitch)]

	if chart.stacked:
		ax.stackplot(
			keys,
			[metric['values'] for metric in metrics],
			labels = [
				metric['metric']
				for metric in metrics
			]
		)
	else:
		for metric in metrics:
			ax.plot(
				keys,
				metric['values'],
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
	web.get('/chart/{chart}', handle),
])

web.run_app(app, host='127.0.0.1', port=12345)
asyncio.get_event_loop().run_until_complete(
	session.close()
)
