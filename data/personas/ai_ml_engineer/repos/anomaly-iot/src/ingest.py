from influxdb_client import InfluxDBClient

write_api = InfluxDBClient(url=URL, token=TOKEN).write_api()
write_api.write(bucket="sensors", record=points)
