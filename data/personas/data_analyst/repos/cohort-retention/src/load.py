from google.cloud import bigquery

client = bigquery.Client()
client.load_table_from_dataframe(df, "analytics.events").result()
