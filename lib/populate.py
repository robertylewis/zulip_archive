"""
This library helps populate a series of JSON files from a
running Zulip instance.

Conceptually it just moves data in one direction:

    Zulip -> file system (JSON files)

This is probably the most technical part of the archive codebase
for now.  Conceptually, it's just connecting to Zulip with the
Python API for Zulip and getting recent messages.

Some of the details are about getting incremental updates from
Zulip.  See `populate_incremental`, but the gist of it is that
we read `latest_id` from the JSON and then use that as the
`anchor` in the API request to Zulip.

About the data:

    The json format for stream_index.json is something like below:

    {
        'time': <the last time stream_index.md was updated>,
        'streams': {
            stream_name: {
                'id': stream_id,
                'latest_id': id of latest post in stream,
                'topic_data': {
                    topic_name: {
                        topic_size: num posts in topic,
                        latest_date: time of latest post }}}}}

    stream_index.json is created in the top level of the JSON directory.

    This directory also contains a subdirectory for each archived stream.

    In each stream subdirectory, there is a json file for each topic in that stream.

    This json file is a list of message objects,
    as desribed at https://zulipchat.com/api/get-messages
"""

import json
import time
from datetime import datetime
from pathlib import Path
from .common import (
        exit_immediately,
        open_outfile,
        sanitize_stream,
        sanitize_topic,
        )

# Takes a list of messages. Returns a dict mapping topic names to lists of messages in that topic.
def separate_results(list):
    map = {}
    for m in list:
        if m['subject'] not in map:
            map[m['subject']] = [m]
        else:
            map[m['subject']].append(m)
    return map

# Retrieves all messages matching request from Zulip, starting at post id anchor.
# As recommended in the Zulip API docs, requests 1000 messages at a time.
# Returns a list of messages.
def request_all(client, request, anchor=0):
    request['anchor'] = anchor
    request['num_before'] = 0
    request['num_after'] = 1000
    response = safe_request(client.get_messages, request)
    msgs = response['messages']
    while not response['found_newest']:
        request['anchor'] = response['messages'][-1]['id'] + 1
        response = safe_request(client.get_messages, request)
        msgs = msgs + response['messages']
    return msgs

# runs client.cmd(args). If the response is a rate limit error, waits
# the requested time and then retries the request.
def safe_request(cmd, *args, **kwargs):
    rsp = cmd(*args, **kwargs)
    while rsp['result'] == 'error':
        print("timeout hit: {}".format(rsp['retry-after']))
        time.sleep(float(rsp['retry-after']) + 1)
        rsp = cmd(*args, **kwargs)
    return rsp

def get_streams(client):
    # In the future, we may want to change this to
    # include_web_public=True, for organizations that might want to
    # use the upcoming web_public flag; but at the very least we
    # should only include public streams.
    response = safe_request(client.get_streams,
                            include_public=True,
                            include_subscribed=False)
    return response['streams']

# Retrieves all messages from Zulip and builds a cache at json_root.
def populate_all(
        client,
        json_root,
        is_valid_stream_name,
        ):
    streams = get_streams(client)
    ind = {}
    for s in (s for s in streams if is_valid_stream_name(s['name'])):
        print(s['name'])
        topics = safe_request(client.get_stream_topics, s['stream_id'])['topics']
        nind = {'id': s['stream_id'], 'latest_id':0}
        tpmap = {}
        for t in topics:
            request = {
                'narrow': [{'operator': 'stream', 'operand': s['name']},
                           {'operator': 'topic', 'operand': t['name']}],
                'client_gravatar': True,
                'apply_markdown': True
            }
            m = request_all(client, request)
            tpmap[t['name']] = {'size': len(m),
                                'latest_date': m[-1]['timestamp']}
            nind['latest_id'] = max(nind['latest_id'], m[-1]['id'])
            out = open_outfile(json_root / Path(sanitize_stream(s['name'], s['stream_id'])),
                               Path(sanitize_topic(t['name']) + '.json'), 'w')
            json.dump(m, out, ensure_ascii=False)
            out.close()
        nind['topic_data'] = tpmap
        ind[s['name']] = nind
    js = {'streams':ind, 'time':datetime.utcfromtimestamp(time.time()).strftime('%b %d %Y at %H:%M')}
    out = open_outfile(json_root, Path('stream_index.json'), 'w')
    json.dump(js, out, ensure_ascii = False)
    out.close()


# Retrieves only new messages from Zulip, based on timestamps from the last update.
# Raises an exception if there is no index at json_root/stream_index.json
def populate_incremental(
        client,
        json_root,
        is_valid_stream_name,
        ):
    streams = get_streams(client)
    stream_index = json_root / Path('stream_index.json')

    if not stream_index.exists():
        error_msg = '''
    You are trying to incrementally update your index, but we cannot find
    a stream index at {}.

    Most likely, you have never built the index.  You can use the -t option
    of this script to build a full index one time.

    (It's also possible that you have built the index but modified the configuration
    or moved files in your file system.)
            '''.format(stream_index)
        exit_immediately(error_msg)

    f = stream_index.open('r', encoding='utf-8')
    stream_index = json.load(f, encoding='utf-8')
    f.close()
    for s in (s for s in streams if is_valid_stream_name(s['name'])):
        print(s['name'])
        if s['name'] not in stream_index['streams']:
            stream_index['streams'][s['name']] = {'id':s['stream_id'], 'latest_id':0, 'topic_data':{}}
        request = {'narrow':[{'operator':'stream', 'operand':s['name']}], 'client_gravatar': True,
                   'apply_markdown': True}
        new_msgs = request_all(client, request, stream_index['streams'][s['name']]['latest_id']+1)
        if len(new_msgs) > 0:
            stream_index['streams'][s['name']]['latest_id'] = new_msgs[-1]['id']
        nm = separate_results(new_msgs)
        for t in nm:
            p = json_root / Path(sanitize_stream(s['name'], s['stream_id'])) / Path(sanitize_topic(t) + '.json')
            topic_exists = p.exists()
            old = []
            if topic_exists:
                f = p.open('r', encoding='utf-8')
                old = json.load(f)
                f.close()
            m = nm[t]
            new_topic_data = {'size': len(m)+len(old),
                                'latest_date': m[-1]['timestamp']}
            stream_index['streams'][s['name']]['topic_data'][t] = new_topic_data
            out = open_outfile(json_root / Path(sanitize_stream(s['name'], s['stream_id'])),
                               Path(sanitize_topic(t) + '.json'), 'w')
            json.dump(old+m, out, ensure_ascii=False)
            out.close()
    stream_index['time'] = datetime.utcfromtimestamp(time.time()).strftime('%b %d %Y at %H:%M')
    out = open_outfile(json_root, Path('stream_index.json'), 'w')
    json.dump(stream_index, out, ensure_ascii = False)
    out.close()
