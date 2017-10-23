from flask_httpauth import HTTPBasicAuth
from flask import request, abort, jsonify, Flask
from werkzeug.security import gen_salt
from flask_cors import CORS, cross_origin
from flask.ext.cache import Cache

import redis
import redis_collections


import json, sys, urllib, os
X_BROKER_API_VERSION = (2, 3)
X_BROKER_API_VERSION_NAME = 'X-Broker-Api-Version'

normal_plan = {
          "id": "normal",
          "name": "normal",
          "description": "A normal version manager." }
# services
vm_service = {'id': 'version_manager_service',
                 'name': 'vms',
                 'description': 'A Version Manager Service',
                 'bindable': True,
                 'tags': ['authz'],
                 'metadata': {"longDescription": "A Version Manager Service"},
                 'plans': [normal_plan]}
app = Flask(__name__)
CORS(app)

auth = HTTPBasicAuth()
@auth.get_password
def get_pw(username):
    if username == '9604a74f-236c-4c4b-a49d-545741525b56':
        return '0ee8201e-c182-4a18-adbb-832c3eff21ba'
    return None

def checkversion(x):
    client_version = [int(y) for y in  x.split('.')]
    comp = [ y - x for x,y in zip(X_BROKER_API_VERSION, client_version) ]
    if comp[0] > 0:
        return True
    if comp[0] <0:
        return False
    if comp[1] <0:
        return False
    else:
        return True
    return false

class ServiceBrokerException(Exception):
    status_code = 400

    def __init__(self, status_code, message, payload=None):
        Exception.__init__(self)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        self.payload = payload
    def to_dict(self):
        rv = dict(self.payload or ())
        rv['error'] = self.message
        return rv

@app.errorhandler(ServiceBrokerException)
def handle_invalid_usage(error):
    response = jsonify(error.to_dict())
    response.status_code = error.status_code
    return response


cf_app_config = json.loads(os.getenv('VCAP_APPLICATION', """{"uris": ["127.0.0.1:8080"]}"""))
cf_service_config = json.loads(os.getenv('VCAP_SERVICES', """{}"""))
app_uri = cf_app_config['uris'][0]

service_instance = "https://" + app_uri + "/cfbroker/{instance_id}"
service_binding = "https://" + app_uri + "/cfbroker/{instance_id}/{binding_id}"
service_dashboard = "https://" + app_uri + "/cfbroker/dashboard/{instance_id}"

if cf_service_config.has_key("p-redis"):
    redis_conn = redis.StrictRedis(host=cf_service_config["p-redis"][0]["credentials"]["host"],
                                   port = cf_service_config["p-redis"][0]["credentials"]["port"],
                                   password = cf_service_config["p-redis"][0]["credentials"]["password"])
    service_instances = redis_collections.Dict(redis=redis_conn, key = "0ffadd92-3cc1-4ca1-a9f6-b786013be119")
    service_bindings = redis_collections.Dict(redis=redis_conn, key = "46da39a9-3830-4c8e-b9f4-eaf3c676aaef")
else:
    service_instances = {}
    service_bindings = {}

@app.route("/getbind")
def getbind():
    referer = request.headers.get("Referer", "https://None.none")
    t, r = urllib.splittype(referer)
    u, r = urllib.splituser(r)
    h, r = urllib.splithost(r)
    shorth = h.split(".")[0]
    for r,s in service_bindings.values():
        if r == shorth:
            be = service_instances[s]
            return be
    return "xxx"

@app.route("/getbind.js")
def getbindjs():
    referer = request.headers.get("Referer", "https://None.none")
    t, r = urllib.splittype(referer)
    u, r = urllib.splituser(r)
    h, r = urllib.splithost(r)
    shorth = h.split(".")[0]
    if  shorth in service_bindings:
        be = service_instances[service_bindings[shorth][1]]
        return """var targethost="%s"; \n"""%be, 200, {'Content-Type': 'application/javascript'}
    return "xxx"

@app.route("/status")
def getstatus():
    return json.dumps({"si": dict(service_instances.items()), "bi": dict(service_bindings.items())})
    
@app.route('/v2/catalog', methods=['GET'])
@auth.login_required
def catalog():
    """
    Return the catalog of services handled
    by this broker
    
    GET /v2/catalog:
    
    HEADER:
        X-Broker-Api-Version: <version>

    return:
        JSON document with details about the
        services offered through this broker
    """
    api_version = request.headers.get('X-Broker-Api-Version')
    if not api_version or not checkversion(api_version):
        raise ServiceBrokerException(409, "Missing or incompatible %s. Expecting version %0.1f or later" % (X_BROKER_API_VERSION_NAME, X_BROKER_API_VERSION))
    return jsonify({"services": [vm_service]})

@app.route('/v2/service_instances/<instance_id>', methods=['PUT'])
@auth.login_required
def provision(instance_id):
    data = request.get_json()
    if data is None or not data.has_key('service_id'):
        raise ServiceBrokerException(422, "Invalid request data")

    service_instances[instance_id] = data["parameters"]["backend_name"]
    return jsonify({"dashboard_url": service_dashboard.format(instance_id=instance_id)}), 201

@app.route('/v2/service_instances/<instance_id>', methods=['DELETE'])
@auth.login_required
def deprovision(instance_id):
    
    #    if not service_instances.has_key(instance_id):
    #        raise ServiceBrokerException(410, "instance not found")
    try:
        service_instances.__delitem__(instance_id)
    except:
        pass
    return jsonify({}), 200

@app.route('/v2/service_instances/<instance_id>/service_bindings/<binding_id>', methods=['PUT'])
@auth.login_required
def bind(instance_id, binding_id):
    print >> sys.stderr, request.data
    data = request.get_json()
    if data is None:
        raise ServiceBrokerException(422, "invalid request data")
    front_uri = data.get("parameters",{}).get("front_uri","")

    service_bindings[front_uri] = (binding_id, instance_id)

    return jsonify({"credentials": {
        "name": "oa_" + binding_id,
        "username": "DUMMY",
        "password": "DUMMY",
        "backend": service_instances[instance_id]
    }}
    )

@app.route('/v2/service_instances/<instance_id>/service_bindings/<binding_id>', methods=['DELETE'])
@auth.login_required
def unbind(instance_id, binding_id):
    for k in service_bindings.keys():
        if service_bindings[k][0] == binding_id:
            service_bindings.__delitem__(k)
            break
    else:
        raise ServiceBrokerException(410, "binding not found")
    return jsonify({}), 200

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=int(os.getenv("VCAP_APP_PORT", "8080")), debug=True)
