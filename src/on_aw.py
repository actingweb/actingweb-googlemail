import logging
import json
from actingweb import on_aw
from src import gmail


class OnAWDemo(on_aw.OnAWBase):

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

    def get_callbacks(self, name):
        """Customizible function to handle GET /callbacks"""
        return False

    def delete_callbacks(self, name):
        """Customizible function to handle DELETE /callbacks"""
        # return True if callback has been processed
        return False

    def post_callbacks(self, name):
        """Customizible function to handle POST /callbacks"""
        gm = gmail.GMail(self.myself, self.config, self.auth)
        try:
            h = gm.process_callback(json.loads(self.webobj.request.body.decode('utf-8')))
        except json.JSONDecodeError:
            return False
        logging.debug(json.dumps(h, indent=4))
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
        gm.cleanup()
        return

    def check_on_oauth_success(self, token=None):
        # THIS METHOD IS CALLED WHEN AN OAUTH AUTHORIZATION HAS BEEN SUCCESSFULLY MADE AND BEFORE APPROVAL
        gm = gmail.GMail(self.myself, self.config, self.auth)
        gm.get_profile()
        self.myself.set_property('email', self.myself.creator)
        return True

    def actions_on_oauth_success(self):
        # THIS METHOD IS CALLED WHEN AN OAUTH AUTHORIZATION HAS BEEN SUCCESSFULLY MADE
        gm = gmail.GMail(self.myself, self.config, self.auth)
        gm.set_up()
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