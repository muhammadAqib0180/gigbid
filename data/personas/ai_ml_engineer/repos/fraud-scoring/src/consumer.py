from confluent_kafka import Consumer

consumer = Consumer({"group.id": "fraud-scoring-scorer", "bootstrap.servers": BROKERS})
consumer.subscribe(["transactions"])
