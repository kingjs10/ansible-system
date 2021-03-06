#!/usr/bin/env python3
import http.client
import json
import os
import sys
from datetime import datetime

# Looking for the main event? It's near the bottom - search for "THE RUN ACTUALLY STARTS HERE"
def get_cloud_provider():
    # more cloud-detect hacks here https://github.com/dgzlopes/cloud-detect/tree/master/cloud_detect/providers
    # test for openstack
    conn = http.client.HTTPConnection('169.254.169.254:80',timeout=5)
    conn.request("GET","/openstack")
    res = conn.getresponse()
    conn.close()
    if res.status == 200: return "p3" # we are pretending all openstacks are p3 for now in case we encounter a different one (like ocp) later

    # test for AWS
    conn = http.client.HTTPConnection('169.254.169.254:80', timeout=5)
    conn.request("GET","/latest/dynamic/instance-identity/document")
    res = conn.getresponse()
    conn.close()
    if res.status == 200: return "aws"
    
    return
    
def get_instance_tags(provider):
    tags = {}
    if provider == 'aws':
        conn = http.client.HTTPConnection('169.254.169.254:80', timeout=5)

        # get some instance details
        conn.request("GET",'/latest/dynamic/instance-identity/document')
        res = conn.getresponse()
        body = res.read().decode('utf-8')
        conn.close
        data = json.loads(body)
        
        # I didn't want this. I wanted to use the AWS API to DescribeTags. The API is mind shredding, and instead of depending on boto
        # I figured it was easier to just expect the aws cli to be here. Seriously, THIS is a nightmare: https://docs.aws.amazon.com/AWSEC2/latest/APIReference/CommonParameters.html
        stream = os.popen('aws ec2 describe-tags --filters "Name=resource-id,Values=' + data['instanceId'] + '" --region ' + data['region'])
        output = stream.read()
        tag_data = json.loads(output)
        for tag in tag_data['Tags']:
            tags[tag['Key']] = tag['Value']

    if provider == 'p3': # other openstack providers should be handled here, don't copy/paste this mess
        conn = http.client.HTTPConnection('169.254.169.254:80',timeout=5)

        # get some instance details
        conn.request("GET",'/openstack/latest/meta_data.json')
        res = conn.getresponse()
        body = res.read().decode('utf-8')
        conn.close
        data = json.loads(body)
        tags = data['meta']

    return tags

def get_ansible_playbooks(tags):
    # if the tag is JSON it must be an array of dictionaries [{'repo': 'vl_users', 'branch': 'master', 'file': 'vl_users.yml'}]
    # otherwise assume the old format and build the array
    try:
        out = json.loads(tags['ansible_playbooks'])
    except Exception as e:
        out = []
        for pb in tags['ansible_playbooks'].split(' '):
            data = pb.split(':')
            out.append({'repo':data[0],'branch':data[1],'file':data[2]})
    return out

def get_git_base_url(provider, tags):
    if tags.__contains__('ansible_git_base_url'): return tags['ansible_git_base_url']
    if provider == 'aws': return 'https://git-codecommit.us-east-1.amazonaws.com/v1/repos/'
    if provider == 'p3': return 'git@sqbu-github.cisco.com:post-deployment/'
    return ''

def get_ansible_extra_args(provider, tags):
    if tags.__contains__('ansible_extra_args'): return tags['ansible_extra_args']
    if provider == 'aws': return '--sleep 60  -i /etc/ansible/local'
    if provider == 'p3': return '--private-key="~/.ssh/id_rsa" --ssh-extra-args="-o IdentitiesOnly=yes -o StrictHostKeyChecking=no -i ~/.ssh/id_rsa" -i localhost'
    return ''

def fail(run,msg):
    run['status'] = 'fail'
    run['message'] = msg
    logger(json.dumps(run))
    sys.exit(run)

def logger(msg):
    # logger is just used to write the run dict out to a dedicated file everything else should go to stdout/stderr
    with open('/var/log/ansible_player_run.log','a') as logfile:
        logfile.write(msg)
        logfile.close()
    print(msg)

def write_ansible_local():
    #we use the ansible /etc/ansible/hosts file to get info so we have to use an inventory file that's just localhost
    if not os.path.exists('/etc/ansible'):
        os.mkdir('/etc/ansible')
    if not os.path.exists('/etc/ansible/local'):
        file = open("/etc/ansible/local", "w+")
        file.write("[hosts] \n127.0.0.1\n")
        file.close()


##### THE RUN ACTUALLY STARTS HERE #####
run = {} # the run dictionary holds all the params which will be used
run['timestamp'] = str(datetime.now())
print('detecting cloud provider')
provider = get_cloud_provider()
if provider == None:
    fail(run,'Unable to detect cloud provider')

print(provider + ' detected - getting instance tags')

# import boto3 here only if aws is detected as the provider since it's on the box because
# the cloud-init needs to install the aws cli which includes boto3
# other cloud providers may need provider specific imports here
#if provider == 'aws': import boto3

tags = get_instance_tags(provider)
if not tags:
    fail(run,'Unable to get instance tags')

if not 'ansible_playbooks' in tags:
    fail(run,'ansible_playbooks attribute not set on instance tags')

run['vcs'] = get_git_base_url(provider, tags)
run['extra_args'] = get_ansible_extra_args(provider, tags)
run['playbooks'] = get_ansible_playbooks(tags)

# with the run dictionary aligned, go ahead and execute

# Provider-specific setup needs to go here
if provider == 'aws':
    os.system("git config --global credential.helper '!aws codecommit credential-helper $@'")
    os.system("git config --global credential.UseHttpPath true")
    ansible_local = write_ansible_local()

for i in range(0,len(run['playbooks'])):
    pb = run['playbooks'][i]
    cmd_to_run = 'ansible-pull ' + run['extra_args'] + ' -d /var/lib/ansible/local/' + pb['repo'] + ' -U ' + run['vcs'] + pb['repo'] + ' -C ' + pb['branch'] + ' ' + pb['file']
    print(cmd_to_run)
    res = os.system(cmd_to_run)
    run['playbooks'][i]['result'] = res
    print("result: ", res)

logger(json.dumps(run))
