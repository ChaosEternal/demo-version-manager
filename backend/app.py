import os
from flask import Flask
from flask_cors import CORS, cross_origin

app = Flask(__name__)
CORS(app)

@app.route("/data")
def helloWorld():
  return "backend Version 1"

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=int(os.getenv("VCAP_APP_PORT")), debug=True)
