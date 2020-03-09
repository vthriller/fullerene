#!/usr/bin/env python
from aiohttp import web, ClientSession
import asyncio
from time import time
from urllib.parse import quote
import json

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
		for metric in data:
			metric['values'] = [
				(k, float(v))
				for k, v in metric['values']
			]
		return web.Response(text=json.dumps(data))

session = ClientSession()

app = web.Application()
app.add_routes([
	web.get('/', handle),
])

web.run_app(app, host='127.0.0.1', port=12345)
asyncio.get_event_loop().run_until_complete(
	session.close()
)
