# vim: tabstop=4 shiftwidth=4 softtabstop=4

#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from heat.common import exception
from heat.engine import clients
from heat.openstack.common import log as logging
from heat.engine import resource
from heat.engine.resources.neutron import neutron

logger = logging.getLogger(__name__)


class VPC(resource.Resource):
    tags_schema = {'Key': {'Type': 'String',
                           'Required': True},
                   'Value': {'Type': 'String',
                             'Required': True}}

    properties_schema = {
        'CidrBlock': {
            'Type': 'String',
            'Description': _('CIDR block to apply to the VPC.')},
        'InstanceTenancy': {
            'Type': 'String',
            'AllowedValues': ['default',
                              'dedicated'],
            'Default': 'default',
            'Implemented': False,
            'Description': _('Allowed tenancy of instances launched in the '
                             'VPC. default - any tenancy; dedicated - '
                             'instance will be dedicated, regardless of '
                             'the tenancy option specified at instance '
                             'launch.')},
        'Tags': {'Type': 'List', 'Schema': {
            'Type': 'Map',
            'Implemented': False,
            'Schema': tags_schema,
            'Description': _('List of tags to attach to the instance.')}}
    }

    def handle_create(self):
        client = self.neutron()
        # The VPC's net and router are associated by having identical names.
        net_props = {'name': self.physical_resource_name()}
        router_props = {'name': self.physical_resource_name()}

        net = client.create_network({'network': net_props})['network']
        client.create_router({'router': router_props})['router']

        self.resource_id_set(net['id'])

    @staticmethod
    def network_for_vpc(client, network_id):
        return client.show_network(network_id)['network']

    @staticmethod
    def router_for_vpc(client, network_id):
        # first get the neutron net
        net = VPC.network_for_vpc(client, network_id)
        # then find a router with the same name
        routers = client.list_routers(name=net['name'])['routers']
        if len(routers) == 0:
            # There may be no router if the net was created manually
            # instead of in another stack.
            return None
        if len(routers) > 1:
            raise exception.Error(
                _('Multiple routers found with name %s') % net['name'])
        return routers[0]

    def check_create_complete(self, *args):
        net = self.network_for_vpc(self.neutron(), self.resource_id)
        if not neutron.NeutronResource.is_built(net):
            return False
        router = self.router_for_vpc(self.neutron(), self.resource_id)
        return neutron.NeutronResource.is_built(router)

    def handle_delete(self):
        from neutronclient.common.exceptions import NeutronClientException
        client = self.neutron()
        router = self.router_for_vpc(client, self.resource_id)
        try:
            client.delete_router(router['id'])
        except NeutronClientException as ex:
            if ex.status_code != 404:
                raise ex

        try:
            client.delete_network(self.resource_id)
        except NeutronClientException as ex:
            if ex.status_code != 404:
                raise ex


def resource_mapping():
    if clients.neutronclient is None:
        return {}

    return {
        'AWS::EC2::VPC': VPC,
    }
