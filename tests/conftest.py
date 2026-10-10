import os

# Keep config imports safe if a test pulls in server packages beyond matcher.
os.environ.setdefault('FEEDGEN_HOSTNAME', 'test.example')
os.environ.setdefault('HOSTNAME', 'test.example')
os.environ.setdefault(
    'FEED_URI',
    'at://did:plc:test/app.bsky.feed.generator/mutualism',
)
os.environ.setdefault('DATABASE_PATH', ':memory:')
# Unit tests stay offline — live DeepSeek scoring is covered with FakeClassifier.
os.environ.setdefault('CLASSIFIER_ENABLED', 'false')
