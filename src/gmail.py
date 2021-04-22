import logging
import time
import base64
import json
from google.cloud import pubsub_v1 as pubsub
from google.api_core import exceptions as google_exceptions

GMAIL_URL = "https://www.googleapis.com/gmail/v1/users/"
# Hardcoded for now
GMAIL_PROJECT = "proud-structure-220107"


class GMail:

    def __init__(self, me=None, config=None, auth=None):
        if not me or not config or not auth:
            return
        self.history_id = me.property.historyId
        if self.history_id:
            self.history_id = int(self.history_id)
        self.topic = me.store.pubsub_topic
        self.subscription = me.store.pubsub_subscription
        self.watch_exp = me.store.watch_expiry
        self.myconf = None
        if self.watch_exp:
            self.watch_exp = int(self.watch_exp)
        self.myself = me
        self.config = config
        self.auth = auth
        self.my_config()

    def my_config(self, **kwargs):
        dirty = False
        if not self.myconf:
            self.myconf = self.myself.property.config
            if self.myconf:
                try:
                    self.myconf = json.loads(self.myconf)
                except json.JSONDecodeError:
                    self.myconf = {}
            else:
                dirty = True
                self.myconf = {}
            if not self.myconf.get('msgHeaders'):
                dirty = True
                self.myconf['msgHeaders'] = [
                        'To',
                        'From',
                        'Subject',
                        'Return-Path',
                        'Thread-Topic',
                        'Thread-Index',
                        'Date',
                        'Content-Language',
                        'Content-Type'
                ]
            if self.myconf.get('watchLabels', None) is None:
                dirty = True
                self.myconf['watchLabels'] = []
            if self.myconf.get('nonWatchLabels', None) is None:
                dirty = True
                self.myconf['nonWatchLabels'] = ['SENT', 'DRAFT']
            if self.myconf.get('msgFormat', None) is None:
                dirty = True
                self.myconf['msgFormat'] = 'metadata'   # ('metadata', 'full', 'raw', 'minimal')
        if kwargs:
            for k, v in kwargs.items():
                if k == 'msgFormat' and v not in ('metadata', 'full', 'raw', 'minimal'):
                    continue
                dirty = True
                self.myconf[k] = v
        if dirty:
            self.myself.property.config = json.dumps(self.myconf)

    def set_up(self, refresh=False):
        if not self._create_pubsub(refresh=refresh):
            return False
        if not self.create_watch(refresh=refresh):
            return False

    def all_ok(self):
        if self.watch_exp and self.topic and self.subscription and self.history_id:
            return True
        return False

    def cleanup(self):
        if not self._stop_watch():
            return False
        if not self._delete_pubsub():
            return False
        return True

    def get_profile(self):
        profile = self.auth.oauth_get(GMAIL_URL + 'me/profile')
        if not profile or self.myself.creator != profile.get('emailAddress'):
            return False
        self.myself.property.messagesTotal = str(profile.get('messagesTotal'))
        self.myself.property.threadsTotal = str(profile.get('threadsTotal'))
        self.myself.property.historyId = str(profile.get('historyId'))
        self.history_id = profile.get('historyId')
        if self.history_id:
            self.history_id = int(self.history_id)
        return True

    def _delete_pubsub(self):
        if self.subscription:
            client = pubsub.SubscriberClient()
            try:
                client.delete_subscription(request={ "subscription": self.subscription})
            except:
                logging.warning('Not able to delete pub/sub subscription ' + self.subscription)
                return False
        if self.topic:
            publisher = pubsub.PublisherClient()
            try:
                publisher.delete_topic(request={"topic": self.topic})
            except:
                logging.warning('Not able to delete pub/sub topic ' + self.topic)
                return False
        return True

    def _create_pubsub(self, refresh=False):
        publisher = pubsub.PublisherClient()
        name = 'projects/' + GMAIL_PROJECT + '/topics/mail-' + self.myself.id
        if not self.topic or refresh:
            try:
                publisher.create_topic(request={"name": name})
            except google_exceptions.AlreadyExists:
                logging.warning('Existing Google pub/sub topic ' + name)
            except (ValueError, google_exceptions.GoogleAPICallError):
                logging.warning('Not able to create Google pub/sub topic ' + name)
                return False
            # Allow gmail to publish to the topic
            policy = {
                "bindings": [{
                    "role": "roles/pubsub.publisher",
                    "members": ["serviceAccount:gmail-api-push@system.gserviceaccount.com"],
                }],
            }
            try:
                response = publisher.set_iam_policy(request={"resource": name, "policy": policy})
            except:
                logging.warning('Not able to add gmail publish permission on ' + name)
                return False
            self.myself.store.pubsub_topic = name
            self.topic = name
        if not self.subscription or refresh:
            sub = 'projects/' + GMAIL_PROJECT + '/subscriptions/mail-' + self.myself.id
            client = pubsub.SubscriberClient()
            try:
                client.create_subscription(
                    request={
                        "name": sub,
                        "topic": name,
                        "push_config": {
                            "push_endpoint": self.config.root + self.myself.id + "/callbacks/messages"
                        },
                        "ack_deadline_seconds": 10,
                        "retainAckedMessages": False
                    })
            except google_exceptions.AlreadyExists:
                logging.warning('Existing Google subscription ' + sub)
            except (ValueError, google_exceptions.GoogleAPICallError):
                logging.warning('Not able to create Google pub/sub subscription ' + sub)
                return False
            self.myself.store.pubsub_subscription = sub
            self.subscription = sub
        return True

    def _stop_watch(self):
        self.auth.oauth_post(GMAIL_URL + 'me/stop')
        if (299 < self.auth.oauth.last_response_code < 199) and self.auth.oauth.last_response_code != 404:
            logging.warning('Not able to stop gmail watch')
            return False
        self.myself.store.watch_expiry = None
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
                self.my_config(watchLabels=labels)
                params['labelFilterAction'] = 'include'
            res = self.auth.oauth_post(GMAIL_URL + 'me/watch', params=params)
            if not res and not self.auth.oauth.last_response_code == 409:
                logging.warning('Not able to create gmail watch')
                return False
            self.watch_exp = res.get('expiration', None)
            self.history_id = res.get('historyId', None)
            if self.watch_exp:
                self.myself.store.watch_expiry = str(self.watch_exp)
            if self.history_id:
                self.myself.property.historyId = str(self.history_id)
        return True

    def get_message(self, id=None, fmt=None):
        """
        Retrieve a specific message from Gmail with id.
        :param id: Gmail message id
        :param fmt: string ('metadata', 'full', 'raw', 'minimal')
        :return: Dict of message data from Gmail or empty dict
        """
        if not id:
            return {}
        if not fmt:
            fmt = self.myconf.get('msgFormat', 'metadata')
        res = self.auth.oauth_get(GMAIL_URL + 'me/messages/' + str(id) + '?format=' + fmt)
        if not res or 'id' not in res:
            return {}
        if 'payload' in res and 'headers' in res['payload']:
            hs = {}
            for h in res['payload']['headers']:
                name = h.get('name')
                if name in self.myconf.get('msgHeaders', []):
                    if name not in hs:
                        hs[name] = []
                    hs[name].append(h.get('value'))
            res['headers'] = hs
            del res['payload']
        return res

    def get_history(self):
        url = GMAIL_URL + 'me/history?historyTypes=messageAdded&startHistoryId=' + str(self.history_id)
        res = self.auth.oauth_get(url)
        logging.debug('Got history: ' + json.dumps(res))
        if not res or not res.get('history'):
            return []
        history = res.get('history')
        history_id = res.get('historyId')
        next_token = res.get('nextPageToken')
        while next_token:
            res = self.auth.oauth_get(GMAIL_URL + 'me/history?historyTypes=messageAdded&startHistoryId=' +
                                      str(self.history_id) + '&pageToken=' + next_token)
            logging.debug('Got history: ' + json.dumps(res))
            if not res or not res.get('history'):
                next_token = None
            else:
                history.append(res.get('history'))
                next_token = res.get('nextPageToken')
        if history_id:
            self.myself.property.historyId = str(history_id)
            self.history_id = history_id
        msgs = {}
        # We have a series of history records
        for h in history:
            # Each history record we can have a series of change types
            for k, v in h.items():
                # Only pick up new messages
                if k != 'messagesAdded':
                    continue
                # There may be multiple messages
                for i in v:
                    found = False
                    if not self.myconf.get('watchLabels'):
                        found = True
                    else:
                        for l in i['message']['labelIds']:
                            if l in self.myconf.get('watchLabels'):
                                found = True
                            break
                    if self.myconf.get('nonWatchLabels'):
                        for l in i['message']['labelIds']:
                            if l in self.myconf.get('nonWatchLabels'):
                                found = False
                            break
                    if found:
                        msgs[i['message']['id']] = {}
        # Add message data
        for k, v in msgs.items():
            msgs[k] = self.get_message(k)
        return msgs

    def process_callback(self, data=None):
        if not data or not data.get('message', {}).get('data', None):
            return False
        msg = data.get('message', {}).get('data', '').encode('utf-8')
        try:
            payload = json.loads(base64.b64decode(msg).decode('utf-8'))
        except json.JSONDecodeError:
            return False
        if not payload or not payload.get('historyId', None):
            return False
        new_id = int(payload.get('historyId'))
        if new_id > self.history_id:
            history = self.get_history()
        else:
            history = {}
        return history
