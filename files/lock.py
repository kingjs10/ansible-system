#!/usr/bin/env python3
import os, boto3, json, decimal, datetime, socket, sys, argparse, logging
from boto3.dynamodb.conditions import Key, Attr
import simplejson as json
from time import sleep

parser = argparse.ArgumentParser()

# Arguments
parser.add_argument("--cluster", required=True, help="cluster name field you want to set")
parser.add_argument("--lock", help="Create a lock based on the hostname and cluster name", action="store_true")
parser.add_argument("--release", help="Release a previously created lock", action="store_true")
parser.add_argument("--status",  help="Find out if the cluster if currently locked", action="store_true")
parser.add_argument("--raw",  help="raw dump from dynamodb query", action="store_true")
parser.add_argument("--full",  help="Find out details of the lock", action="store_true")
parser.add_argument("--purge",  help="delete the lock no matter the owner", action="store_true")


args = parser.parse_args()





dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('LockTable')
current_time = datetime.datetime.utcnow()
response = table.scan(FilterExpression = Attr('cluster').eq(args.cluster))
items = response['Items']
hostname = socket.gethostname()

###Logging
logging.basicConfig(filename='/var/log/syslog',format='%(asctime)s  %(message)s', level=logging.INFO, datefmt='%b %d %H:%M:%S',)

###exit codes
return_ok = 0
return_locked = 1
return_not_owner = 2

try:
    if (items[0]['owner']) == hostname:
        owner = hostname
except IndexError:
    owner = "no_owner"
###########################################################
if args.lock:


#create the lock with hostname
    if items ==[]:
        put = table.put_item(
        Item={
                'owner': socket.gethostname(),
                'cluster': args.cluster,
                'time': str(current_time)
            }
        )

        sleep(0.5)
        response2 = table.scan(FilterExpression = Attr('cluster').eq(args.cluster),  ConsistentRead=True)
        items2 = response2['Items']

        try:
            if (items2[0]['owner']) == hostname:
                owner = hostname
        except IndexError:
            owner = "not_owner"


        if owner == hostname:
            print('locked - ', (items2[0]['owner']))
            logging.info('% s cluster-lock % s  locked - % s' %(hostname, args.cluster, (items2[0]['owner'])))
            sys.exit(return_ok)
        else:
            print('lock failed - ', owner)
            logging.info('% s cluster-lock % s lock failed - % s' %(hostname, args.cluster, owner))
            sys.exit(return_not_owner)



    else:
        print("already locked - ", (items[0]['owner']))
        logging.info('% s cluster-lock % s cluster is already locked - % s' %(hostname, args.cluster, (items[0]['owner'])))
        sys.exit(return_locked)

###########################################################
if args.status:
    if items ==[]:
        print("unlocked")
        logging.info('% s cluster-lock % s cluster is unlocked' %(hostname, args.cluster))


    else:
        print('locked - ',(items[0]['owner']))



###########################################################
if args.release:
    try:
        if (items[0]['owner']) == hostname:
            delete = table.delete_item(
                Key=
                {
                        'cluster': args.cluster
                }
            )
            print('released')
            logging.info('% s cluster-lock % s cluster lock released - % s' %(hostname, args.cluster, (items[0]['owner'])))
            sys.exit(return_ok)


        else:
            print('lock held by someone else - ', (items[0]['owner']))
            sys.exit(return_not_owner)
    except IndexError:
        print(' lock held by someone else - ', (items[0]['owner']))
        sys.exit(return_not_owner)

###########################################################

if args.full:
    if items ==[]:
        print("no lock found")

    else:
        print(json.dumps(items, indent=5))

###########################################################

if args.raw:
    if items ==[]:
        print("no lock found")

    else:
        print(json.dumps(response, indent=5))

###########################################################
if args.purge:

            delete = table.delete_item(
                Key=
                {
                        'cluster': args.cluster
                }
            )
            print('purged')
            logging.info('% s cluster-lock % s cluster lock purged - % s' %(hostname, args.cluster, (items[0]['owner'])))
            sys.exit(return_ok)


