import logging
import json
import time
from actingweb import on_aw
from src import gmail

PROP_HIDE = []

PROP_PROTECT = PROP_HIDE + [
    "new",
    "historyId",
    "messagesTotal",
    "threadsTotal"
]


class OnAWGoogleMail(on_aw.OnAWBase):

    def bot_post(self, path):
        """Called on POSTs to /bot.

        Note, there will not be any actor initialised.
        """

        # Safety valve to make sure we don't do anything if bot is not
        # configured.
        if not self.config.bot['token'] or len(self.config.bot['token']) == 0:
            return False

        # try:
        #     body = json.loads(req.request.body.decode('utf-8', 'ignore'))
        #     logging.debug('Bot callback: ' + req.request.body.decode('utf-8', 'ignore'))
        # except:
        #     return 405
        #
        # This is how actor can be initialised if the bot request
        # contains a value that has been stored as an actor property.
        # This value must be a primary key for the external oauth identity
        # that the actor is representing.
        # Here, oauthId (from oauth service) has earlier been stored as a property
        # myself = actor.Actor()
        # myself.get_from_property(name='oauthId', value=<PROPERTY-VALUE>)
        # if myself.id:
        #    logging.debug('Found Actor(' + myself.id + ')')
        #
        # If we havent''
        # if not myself.id:
        #    myself.create(url=self.config.root, creator= <EMAIL>,
        #                    passphrase=self.config.new_token())
        #    Now store the oauthId propery
        #    myself.set_property('oauthId', <ID-VALUE>)
        #    Send confirmation message that actor has been created
        #    return True
        # Do something
        return True

    def get_properties(self, path: list, data: dict) -> dict or None:
        """ Called on GET to properties for transformations to be done
        :param path: Target path requested
        :type path: list[str]
        :param data: Data retrieved from data store to be returned
        :type data: dict
        :return: The transformed data to return to requestor or None if 404 should be returned
        :rtype: dict or None
        """
        if not path:
            for k, v in data.copy().items():
                if k in PROP_HIDE:
                    del data[k]
        elif len(path) > 0 and path[0] in PROP_HIDE:
            return None
        return data

    def delete_properties(self, path: list, old: dict, new: dict) -> bool:
        """ Called on DELETE to properties
        :param path: Target path to be deleted
        :type path: list[str]
        :param old: Property value that will be deleted (or changed)
        :type old: dict
        :param new: Property value after path has been deleted
        :type new: dict
        :return: True if DELETE is allowed, False if 403 should be returned
        :rtype: bool
        """
        if len(path) > 0 and path[0] in PROP_PROTECT:
            return False
        return True

    def put_properties(self, path: list, old: dict, new: dict) -> dict or None:
        """ Called on PUT to properties for transformations to be done before save
        :param path: Target path requested to be updated
        :type path: list[str]
        :param old: Old data from database
        :type old: dict
        :param new:
        :type new: New data from PUT request (after merge)
        :return: The dict that should be stored or None if 400 should be returned and nothing stored
        :rtype: dict or None
        """
        if not path:
            return None
        elif len(path) > 0 and path[0] in PROP_PROTECT:
            return None
        if path and len(path) >= 1 and path[0] == 'config':
            if 'watchLabels' in new:
                new_labels = new['watchLabels']
                gm = gmail.GMail(self.myself, self.config, self.auth)
                gm.create_watch(labels=new_labels, refresh=True)
        return new

    def post_properties(self, prop: str, data: dict) -> dict or None:
        """ Called on POST to properties, once for each property
        :param prop: Property to be created
        :type prop: str
        :param data: The data to be stored in prop
        :type data: dict
        :return: The transformed data to store in prop or None if that property should be skipped and not stored
        :rtype: dict or None
        """
        if not prop:
            return None
        elif prop in PROP_PROTECT:
            return None
        return data

    def get_callbacks(self, name):
        """Customizible function to handle GET /callbacks"""
        return False

    def delete_callbacks(self, name):
        """Customizible function to handle DELETE /callbacks"""
        # return True if callback has been processed
        return False

    def post_callbacks(self, name):
        """Customizible function to handle POST /callbacks"""
        if name == 'messages':
            gm = gmail.GMail(self.myself, self.config, self.auth)
            try:
                h = gm.process_callback(json.loads(self.webobj.request.body.decode('utf-8')))
            except json.JSONDecodeError:
                return False
            logging.debug('Processed google callback: ' + json.dumps(h, indent=4))
            if h:
                blob = json.dumps(h)
                self.myself.property.new = blob
                self.myself.register_diffs(target='properties', subtarget='new', blob=blob)
            now = time.time()
            if not gm.watch_exp or now > gm.watch_exp - (3 * 24 * 3600):
                logging.debug('Less than 3 x 24h to gmail watch expiry, refreshing...')
                gm.set_up(refresh=True)
        return True

    def post_subscriptions(self, sub, peerid, data):
        """Customizible function to process incoming callbacks/subscriptions/ callback with json body,
        return True if processed, False if not."""
        logging.debug("Got callback and processed " + sub["subscriptionid"] +
                      " subscription from peer " + peerid + " with json blob: " + json.dumps(data))
        return True

    def delete_actor(self):
        # THIS METHOD IS CALLED WHEN AN ACTOR IS REQUESTED TO BE DELETED.
        # THE BELOW IS SAMPLE CODE
        # Clean up anything associated with this actor before it is deleted.
        # END OF SAMPLE CODE
        gm = gmail.GMail(self.myself, self.config, self.auth)
        if gm.cleanup():
            return True
        else:
            return False

    def check_on_oauth_success(self, token=None):
        # THIS METHOD IS CALLED WHEN AN OAUTH AUTHORIZATION HAS BEEN SUCCESSFULLY MADE AND BEFORE APPROVAL
        gm = gmail.GMail(self.myself, self.config, self.auth)
        gm.get_profile()
        return True

    def actions_on_oauth_success(self):
        # THIS METHOD IS CALLED WHEN AN OAUTH AUTHORIZATION HAS BEEN SUCCESSFULLY MADE
        gm = gmail.GMail(self.myself, self.config, self.auth)
        gm.set_up(refresh=True)
        return gm.all_ok()

    def get_resources(self, name):
        """ Called on GET to resources. Return struct for json out.

            Returning {} will give a 404 response back to requestor.
        """
        return {}

    def delete_resources(self, name):
        """ Called on DELETE to resources. Return struct for json out.

            Returning {} will give a 404 response back to requestor.
        """
        return {}

    def put_resources(self, name, params):
        """ Called on PUT to resources. Return struct for json out.

            Returning {} will give a 404 response back to requestor.
            Returning an error code after setting the response will not change
            the error code.
        """
        return {}

    def post_resources(self, name, params):
        """ Called on POST to resources. Return struct for json out.

            Returning {} will give a 404 response back to requestor.
            Returning an error code after setting the response will not change
            the error code.
        """
        return {}

    def www_paths(self, path=''):
        # THIS METHOD IS CALLED WHEN AN actorid/www/* PATH IS CALLED (AND AFTER ACTINGWEB
        # DEFAULT PATHS HAVE BEEN HANDLED)
        # THE BELOW IS SAMPLE CODE
        # if path == '' or not myself:
        #    logging.info('Got an on_www_paths without proper parameters.')
        #    return False
        # if path == 'something':
        #    return True
        # END OF SAMPLE CODE
        return False
