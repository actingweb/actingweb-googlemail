import logging
import time
import base64
import json

GMAIL_URL = "https://www.googleapis.com/gmail/v1/users/"
PUBSUB_URL = "https://pubsub.googleapis.com/v1/"
GMAIL_PROJECT = "proud-structure-220107"


class GMail:

    def __init__(self, me=None, config=None, auth=None):
        if not me or not config or not auth:
            return
        self.historyId = me.get_property('historyId').value
        if self.historyId:
            self.historyId = int(self.historyId)
        self.labels = None
        self.topic = me.get_property('pubsub-topic').value
        self.subscription = me.get_property('pubsub-subscription').value
        self.watch_exp = me.get_property('watch-expiry').value
        if self.watch_exp:
            self.watch_exp = int(self.watch_exp)
        self.myself = me
        self.config = config
        self.auth = auth

    def set_up(self):
        if not self._create_pubsub():
            return False
        if not self.create_watch():
            return False

    def all_ok(self):
        if self.watch_exp and self.topic and self.subscription and self.historyId:
            return True
        return False

    def cleanup(self):
        if not self._stop_watch():
            return False
        if not self._delete_pubsub():
            return False
        return True

    def get_profile(self):
        profile = self.auth.oauth_get('https://www.googleapis.com/gmail/v1/users/me/profile')
        if not profile or self.myself.creator != profile.get('emailAddress'):
            return False
        self.myself.set_property('messagesTotal', str(profile.get('messagesTotal')))
        self.myself.set_property('threadsTotal', str(profile.get('threadsTotal')))
        self.myself.set_property('historyId', str(profile.get('historyId')))
        self.historyId = profile.get('historyId')
        if self.historyId:
            self.historyId = int(self.historyId)
        return True

    def _delete_pubsub(self):
        if self.subscription:
            self.auth.oauth_delete(PUBSUB_URL + self.subscription)
            if 199 > self.auth.oauth.last_response_code > 299:
                logging.warning('Not able to delete pub/sub subscription ' + self.subscription)
                return False
        if self.topic:
            self.auth.oauth_delete(PUBSUB_URL + self.topic)
            if 199 > self.auth.oauth.last_response_code > 299:
                logging.warning('Not able to delete pub/sub topic ' + self.topic)
                return False
        return True

    def _create_pubsub(self, refresh=False):
        if not self.topic or refresh:
            name = 'projects/'+ GMAIL_PROJECT + '/topics/mail-' + self.myself.id
            res = self.auth.oauth_put(PUBSUB_URL + name)
            if not res and not self.auth.oauth.last_response_code == 409:
                logging.warning('Not able to create Google pub/sub topic ' + name)
                return False
            # Allow gmail to publish to the topic
            params = {
                "policy": {
                    "bindings": [{
                        "role": "roles/pubsub.publisher",
                        "members": ["serviceAccount:gmail-api-push@system.gserviceaccount.com"],
                    }],
                }
            }
            res = self.auth.oauth_post(PUBSUB_URL + name + ':setIamPolicy', params=params)
            if not res and not self.auth.oauth.last_response_code == 409:
                logging.warning('Not able to add gmail publish permission on ' + name)
                return False
            self.myself.set_property('pubsub-topic', name)
            self.topic = name
        if not self.subscription or refresh:
            sub = 'projects/' + GMAIL_PROJECT + '/subscriptions/mail-' + self.myself.id
            # New subscription
            params = {
                "topic": name,
                "pushConfig": {
                    "pushEndpoint": self.config.root + self.myself.id + '/callbacks/messages'
                },
                "ackDeadlineSeconds": 10,
                "retainAckedMessages": False
            }
            res = self.auth.oauth_put(PUBSUB_URL + sub, params=params)
            if not res and not self.auth.oauth.last_response_code == 409:
                logging.warning('Not able to create Google pub/sub subscription ' + sub)
                return False
            self.myself.set_property('pubsub-subscription', sub)
            self.subscription = sub
        return True

    def _stop_watch(self):
        self.auth.oauth_post(GMAIL_URL + 'me/stop')
        if 199 > self.auth.oauth.last_response_code > 299 and self.auth.oauth.last_response_code != 404:
            logging.warning('Not able to stop gmail watch')
            return False
        self.myself.delete_property('watch-expiry')
        self.watch_exp = None
        return True

    def create_watch(self, labels=None, refresh=False):
        now = time.time()
        if not self.watch_exp or now > self.watch_exp - (24 * 3600) or refresh:
            params = {
                "topicName": self.topic
            }
            if labels:
                params['labelIds'] = labels
                self.labels = labels
                params['labelFilterAction'] = 'include'
            res = self.auth.oauth_post(GMAIL_URL + 'me/watch', params=params)
            if not res and not self.auth.oauth.last_response_code == 409:
                logging.warning('Not able to create gmail watch')
                return False
            self.watch_exp = res.get('expiration', None)
            self.historyId = res.get('historyId', None)
            if self.watch_exp:
                self.myself.set_property('watch-expiry', str(self.watch_exp))
            if self.historyId:
                self.myself.set_property('historyId', str(self.historyId))
        return True

    def get_message(self, id=None):
        if not id:
            return {}
        res = self.auth.oauth_get(GMAIL_URL + 'me/messages/' + str(id) + '?format=metadata')
        if not res or 'id' not in res:
            return {}
        return res

    def get_history(self, id=0):
        if id == 0:
            id = self.historyId
        url = GMAIL_URL + 'me/history?startHistoryId=' + str(self.historyId)
        res = self.auth.oauth_get(url)
        logging.debug('Got history: ' + json.dumps(res))
        if not res or not res.get('history'):
            return []
        history = res.get('history')
        history_id = res.get('historyId')
        nextToken = res.get('nextPageToken')
        while nextToken:
            res = self.auth.oauth_get(GMAIL_URL + 'me/history?startHistoryId=' + str(self.historyId) +
                                      '&pageToken=' + nextToken)
            logging.debug('Got history: ' + json.dumps(res))
            if not res or not res.get('history'):
                nextToken = None
            history.append(res.get('history'))
            nextToken = res.get('nextPageToken')
        if history_id:
            self.myself.set_property('historyId', str(history_id))
            self.historyId = history_id
        msgs = {}
        # We have a series of history records
        for h in history:
            # Each history record we can have a series of change types
            for k, v in h.items():
                # Skip list of all messages
                if k in 'messages':
                    continue
                # Only pick up new messages
                if k not in 'messagesAdded':
                    continue
                # if k not in ('labelsAdded', 'labelsRemoved', 'messagesAdded', 'messagesDeleted'):
                    # if k in 'messages':
                    #     for i in v:
                    #         msgs[i['id']] = {
                    #             'thread': i['threadId']
                    #         }
                    # continue
                # For each change type, there may be multiple messages
                for i in v:
                    msgs[i['message']['id']] = {
                        'thread': i['message']['threadId'],
                        'labels': i['message']['labelIds']
                    }
        # Add full messages
        for k, v in msgs.items():
            msgs[k]['message'] = self.get_message(k)
        return msgs

    def process_callback(self, data=None):
        if not data or not data.get('message',{}).get('data', None):
            return False
        msg = data.get('message', {}).get('data', '').encode('utf-8')
        try:
            payload = json.loads(base64.b64decode(msg).decode('utf-8'))
        except json.JSONDecodeError:
            return False
        if not payload or not payload.get('historyId', None):
            return False
        newId = int(payload.get('historyId'))
        history = self.get_history(newId)
        return history
