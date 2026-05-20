from dotenv import load_dotenv
load_dotenv()
import os, requests
from simple_salesforce import Salesforce

r = requests.post(
    f'https://{os.getenv("SF_ORG_DOMAIN")}/services/oauth2/token',
    data={
        'grant_type': 'client_credentials',
        'client_id': os.getenv('SF_CONSUMER_KEY'),
        'client_secret': os.getenv('SF_CONSUMER_SECRET'),
    }
)
sf = Salesforce(instance_url=r.json()['instance_url'], session_id=r.json()['access_token'])
result = sf.query("SELECT Name, Active__c FROM Account WHERE Name IN ('Check24', 'HappyCar') LIMIT 2")
for rec in result['records']:
    print(f"{rec['Name']}: Active__c = {repr(rec['Active__c'])} (type: {type(rec['Active__c']).__name__})")
