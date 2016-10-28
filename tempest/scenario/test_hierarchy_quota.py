# Copyright 2012 OpenStack Foundation
# All Rights Reserved.
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

import json
import re

from tempest import clients as tempest_clients
from tempest.common import credentials_factory
from tempest import config
from tempest.lib.common.utils import test_utils
from tempest.scenario import manager
from tempest import test

CONF = config.CONF


class TestHierarchyQuota(manager.ScenarioTest):

    def setUp(self):
        super(TestHierarchyQuota, self).setUp()
        self.admin_client = self.get_client_manager(
            credential_type='admin')
        roles_map = {role['name']: role for role in
                     self.admin_client.roles_client.list_roles()['roles']}
        self.admin_role_id = roles_map[CONF.identity.admin_role]['id']
        self.member_role_id = roles_map['_member_']['id']

    def _create_project(self, name, parent=None):
        params = {}
        if parent:
            params['parent_id'] = parent
        project = self.admin_client.projects_client.create_project(
            name, **params)['project']
        self.addCleanup(
            self.admin_client.projects_client.delete_project,
            project['id'])
        user = self.admin_client.users_client.create_user(
            name='%s-user' % name, password='fake_pass',
            project_id=project['id'])['user']
        self.addCleanup(self.admin_client.users_client.delete_user,
                        user['id'])
        self.admin_client.roles_client.create_user_role_on_project(
            project['id'], user['id'], self.admin_role_id)
        project['user'] = user
        return project

    def _create_server(self, project, **kwargs):
        creds = credentials_factory.get_credentials(
            fill_in=False, identity_version='v3',
            **{'user_id': project['user']['id'],
               'password': 'fake_pass',
               'project_name': project['name']})
        client = tempest_clients.Manager(creds).servers_client
        kwargs['flavorRef'] = CONF.compute.flavor_ref
        kwargs['imageRef'] = CONF.compute.image_ref
        server = client.create_server(**kwargs)['server']
        self.addCleanup(
            self.admin_client.servers_client.delete_server,
            server['id'])
        return server

    def test_hierarchy_limits_work(self):
        """
             /-b, 1
        -a, 3
             \-c, 2

        tree.use('a', 1)  # ok
        tree.use('b', 1)  # ok
        tree.use('c', 2)  # fail
        """
        a = self._create_project('A')
        b = self._create_project('B', a['id'])
        c = self._create_project('C', a['id'])
        update_quota = self.admin_client.quotas_client.update_quota_set
        update_quota(a['id'], instances=3)
        update_quota(b['id'], instances=1)
        update_quota(c['id'], instances=2)
        self._create_server(a, name='instance-a')
        self._create_server(b, name='instance-b')
        self._create_server(c, name='instance-c-1')
        self.assertRaises(tempest.lib.exceptions.Forbidden,
                          self._create_server, c, name='instance-c-2')
