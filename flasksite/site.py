
import flask

app = flask.Flask(__name__)


@app.route('/')
def hello_world():
    print('this is log to stdout')
    return 'Hello, World!'
