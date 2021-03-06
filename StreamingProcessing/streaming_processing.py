# 1, read from kafka, kafka broker, kafka topic
# 2, write data back to Kafka, Kafka broker, Kafka topic
# under the current path and run spark-submit --jars *.jar streaming_processing.py

import sys
import atexit
import logging
import json
import time
from pyspark import SparkContext
from pyspark.streaming import StreamingContext
from pyspark.streaming.kafka import KafkaUtils
from Kafka import KafkaProducer
from Kafka.errors import KafkaError, KafkaTimeoutError
from ast import literal_eval

topic = 'running-analyzer'
new_topic = 'average-running-analyzer'
kafka_broker = '192.168.99.100:9092'
logger_format = '%(asctime)-15s %(message)s'
logging.basicConfig(format=logger_format)
logger = logging.getLogger('stream-process')
logger.setLevel(logging.INFO)

def process_stream(stream):
    def send_to_kafka(rdd):
        results = rdd.collect()
        for r in results:
            data = json.dumps(
                {
                    'symbol' : r[0],
                    'timestamp' : time.time(),
                    'average_distance' : int(r[1][0]) / int(r[1][1])
                }
            )
            print('data:', data.encode('utf-8'))
            try:
                logger.info('Sending average distance %s to Kafka' %data)
                kafka_producer.send(new_topic, value = data.encode('utf-8'))
            except KafkaError as error:
                logger.warn('Failed to send average running to Kafka, casued by %s', error.message)

    def pair(data):
        record = json.loads(literal_eval(data[1]))[0]
        print(record.get('runningSymbol'), '---', (float(record.get('LastRuningDistance')), 1))
        return record.get('runningSymbol'), (float(record.get('LastRuningDistance')), 1)

    # def pair2(symbol, x_y): # missing 1 required positional argument: 'x_y'
    #     return symbol, x_y[0] / x_y[1]
    # stream receive not just one message at the same time, so it use reduceByKey
    stream.map(pair).reduceByKey(lambda a, b: (a[0] + b[0], a[1] + b[1])).foreachRDD(send_to_kafka)

def shutdown_hook(producer):
    try:
        logger.info('Flush pending messages to Kafka')
        # - flush(10) 10 is ten seconds timeout
        producer.flush(10)
        logger.info('Finish flushing pending message')
    except KafkaError as kafka_error:
        logger.warn('Failed to flush pending message to Kafka')
    finally:
        try:
            producer.close(10)
        except Exception as e:
            logger.warn('Failed to close Kafka connection')
        logger.info('Finish closing Kafka producer')

if __name__ == '__main__':
    # if(len(sys.argv) != 4):
    #     print('Usage: streaming processing [topic] [new_topic] [kafka_broker]')
    #     exit(1)
    # topic, new_topic, kafka_borker = sys.argv[1:]
    # - setup connection to spark cluster
    # - 2 means how many cores we use for computation
    # - spark program name
    sc = SparkContext('local[2]', 'runningAveragePrice')
    # - spark has its own logger
    sc.setLogLevel('ERROR')
    # - similar to water tap, open water tap per 5 seconds to handle data
    ssc = StreamingContext(sc, 5)
    # - create a data stream from spark
    # directKafkaStream = KafkaUtils.createStream(ssc, kafka_borker, 'spark-streaming-consumer',{topic : 1})
    directKafkaStream = KafkaUtils.createDirectStream(ssc, [topic], {'metadata.broker.list' : kafka_broker})
    # - for each RDD, do something
    process_stream(directKafkaStream)
    # - instantiate Kafka producer
    kafka_producer = KafkaProducer(bootstrap_servers=kafka_broker)
    # - setup proper shutdown hook
    atexit.register(shutdown_hook, kafka_producer)
    ssc.start()
    ssc.awaitTermination()

