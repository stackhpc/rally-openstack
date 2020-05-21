# Copyright 2017: Mirantis Inc.
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

import os

import ddt
import mock
import requests

from rally.common import cfg
from rally import exceptions
from rally_openstack.verification.tempest import config
from rally_openstack.verification.tempest import context
from tests.unit import fakes
from tests.unit import test


CONF = cfg.CONF


CRED = {
    "username": "admin",
    "tenant_name": "admin",
    "password": "admin-12345",
    "auth_url": "http://test:5000/v2.0/",
    "permission": "admin",
    "region_name": "test",
    "https_insecure": False,
    "https_cacert": "/path/to/cacert/file",
    "user_domain_name": "admin",
    "project_domain_name": "admin"
}

PATH = "rally_openstack.verification.tempest.context"


@ddt.ddt
class TempestContextTestCase(test.TestCase):

    def setUp(self):
        super(TempestContextTestCase, self).setUp()

        self.mock_isfile = mock.patch("os.path.isfile",
                                      return_value=True).start()

        self.cred = fakes.FakeCredential(**CRED)
        self.deployment = fakes.FakeDeployment(
            uuid="fake_deployment", admin=self.cred)
        cfg = {"verifier": mock.Mock(deployment=self.deployment),
               "verification": {"uuid": "uuid"}}
        cfg["verifier"].manager.home_dir = "/p/a/t/h"
        cfg["verifier"].manager.configfile = "/fake/path/to/config"
        self.context = context.TempestContext(cfg)
        self.context.conf.add_section("compute")
        self.context.conf.add_section("orchestration")
        self.context.conf.add_section("scenario")

    @mock.patch("six.moves.builtins.open", side_effect=mock.mock_open(),
                create=True)
    def test__download_image_from_glance(self, mock_open):
        self.mock_isfile.return_value = False
        img_path = os.path.join(self.context.data_dir, "foo")
        img = mock.MagicMock()
        glanceclient = self.context.clients.glance()
        glanceclient.images.data.return_value = "data"

        self.context._download_image_from_source(img_path, img)
        mock_open.assert_called_once_with(img_path, "wb")
        glanceclient.images.data.assert_called_once_with(img.id)
        mock_open().write.assert_has_calls([mock.call("d"),
                                            mock.call("a"),
                                            mock.call("t"),
                                            mock.call("a")])

    @mock.patch("six.moves.builtins.open", side_effect=mock.mock_open())
    @mock.patch("requests.get", return_value=mock.MagicMock(status_code=200))
    def test__download_image_from_url_success(self, mock_get, mock_open):
        self.mock_isfile.return_value = False
        img_path = os.path.join(self.context.data_dir, "foo")
        mock_get.return_value.iter_content.return_value = "data"

        self.context._download_image_from_source(img_path)
        mock_get.assert_called_once_with(CONF.openstack.img_url, stream=True)
        mock_open.assert_called_once_with(img_path, "wb")
        mock_open().write.assert_has_calls([mock.call("d"),
                                            mock.call("a"),
                                            mock.call("t"),
                                            mock.call("a")])

    @mock.patch("requests.get")
    @ddt.data(404, 500)
    def test__download_image_from_url_failure(self, status_code, mock_get):
        self.mock_isfile.return_value = False
        mock_get.return_value = mock.MagicMock(status_code=status_code)
        self.assertRaises(exceptions.RallyException,
                          self.context._download_image_from_source,
                          os.path.join(self.context.data_dir, "foo"))

    @mock.patch("requests.get", side_effect=requests.ConnectionError())
    def test__download_image_from_url_connection_error(
            self, mock_requests_get):
        self.mock_isfile.return_value = False
        self.assertRaises(exceptions.RallyException,
                          self.context._download_image_from_source,
                          os.path.join(self.context.data_dir, "foo"))

    @mock.patch("rally_openstack.wrappers."
                "network.NeutronWrapper.create_network")
    @mock.patch("six.moves.builtins.open", side_effect=mock.mock_open())
    def test_options_configured_manually(
            self, mock_open, mock_neutron_wrapper_create_network):
        self.context.available_services = ["glance", "heat", "nova", "neutron"]

        self.context.conf.set("compute", "image_ref", "id1")
        self.context.conf.set("compute", "image_ref_alt", "id2")
        self.context.conf.set("compute", "flavor_ref", "id3")
        self.context.conf.set("compute", "flavor_ref_alt", "id4")
        self.context.conf.set("compute", "fixed_network_name", "name1")
        self.context.conf.set("orchestration", "instance_type", "id5")
        self.context.conf.set("scenario", "img_file", "id6")

        self.context.__enter__()

        glanceclient = self.context.clients.glance()
        novaclient = self.context.clients.nova()

        self.assertEqual(0, glanceclient.images.create.call_count)
        self.assertEqual(0, novaclient.flavors.create.call_count)
        self.assertEqual(0, mock_neutron_wrapper_create_network.call_count)

    def test__create_tempest_roles(self):
        role1 = CONF.openstack.swift_operator_role
        role2 = CONF.openstack.swift_reseller_admin_role
        role3 = CONF.openstack.heat_stack_owner_role
        role4 = CONF.openstack.heat_stack_user_role

        client = self.context.clients.verified_keystone()
        client.roles.list.return_value = [fakes.FakeRole(name=role1),
                                          fakes.FakeRole(name=role2)]
        client.roles.create.side_effect = [fakes.FakeFlavor(name=role3),
                                           fakes.FakeFlavor(name=role4)]

        self.context._create_tempest_roles()
        self.assertEqual(2, client.roles.create.call_count)

        created_roles = [role.name for role in self.context._created_roles]
        self.assertIn(role3, created_roles)
        self.assertIn(role4, created_roles)

    @mock.patch("rally_openstack.services.image.image.Image")
    def test__discover_image(self, mock_image):
        client = mock_image.return_value
        client.list_images.return_value = [fakes.FakeImage(name="Foo"),
                                           fakes.FakeImage(name="CirrOS")]

        image = self.context._discover_image()
        self.assertEqual("CirrOS", image.name)

    @mock.patch("six.moves.builtins.open", side_effect=mock.mock_open(),
                create=True)
    @mock.patch("rally_openstack.services.image.image.Image")
    @mock.patch("os.path.isfile", return_value=False)
    def test__download_image(self, mock_isfile, mock_image, mock_open):
        img_1 = mock.MagicMock()
        img_1.name = "Foo"
        img_2 = mock.MagicMock()
        img_2.name = "CirrOS"
        glanceclient = self.context.clients.glance()
        glanceclient.images.data.return_value = "data"
        mock_image.return_value.list_images.return_value = [img_1, img_2]

        self.context._download_image()
        img_path = os.path.join(self.context.data_dir, self.context.image_name)
        mock_image.return_value.list_images.assert_called_once_with(
            status="active", visibility="public")
        glanceclient.images.data.assert_called_once_with(img_2.id)
        mock_open.assert_called_once_with(img_path, "wb")
        mock_open().write.assert_has_calls([mock.call("d"),
                                            mock.call("a"),
                                            mock.call("t"),
                                            mock.call("a")])

    # We can choose any option to test the '_configure_option' method. So let's
    # configure the 'flavor_ref' option.
    def test__configure_option(self):
        helper_method = mock.MagicMock()
        helper_method.side_effect = [fakes.FakeFlavor(id="id1")]

        self.context.conf.set("compute", "flavor_ref", "")
        self.context._configure_option("compute", "flavor_ref",
                                       helper_method=helper_method, flv_ram=64,
                                       flv_disk=5)
        self.assertEqual(1, helper_method.call_count)

        result = self.context.conf.get("compute", "flavor_ref")
        self.assertEqual("id1", result)

    @mock.patch("rally_openstack.services.image.image.Image")
    def test__discover_or_create_image_when_image_exists(self, mock_image):
        client = mock_image.return_value
        client.list_images.return_value = [fakes.FakeImage(name="CirrOS")]

        image = self.context._discover_or_create_image()
        self.assertEqual("CirrOS", image.name)
        self.assertEqual(0, client.create_image.call_count)
        self.assertEqual(0, len(self.context._created_images))

    @mock.patch("rally_openstack.services.image.image.Image")
    def test__discover_or_create_image(self, mock_image):
        client = mock_image.return_value

        image = self.context._discover_or_create_image()
        self.assertEqual(image, mock_image().create_image.return_value)
        self.assertEqual(self.context._created_images[0],
                         client.create_image.return_value)
        params = {"container_format": CONF.openstack.img_container_format,
                  "image_location": mock.ANY,
                  "disk_format": CONF.openstack.img_disk_format,
                  "image_name": mock.ANY,
                  "visibility": "public"}
        client.create_image.assert_called_once_with(**params)

    def test__discover_or_create_flavor_when_flavor_exists(self):
        client = self.context.clients.nova()
        client.flavors.list.return_value = [fakes.FakeFlavor(id="id1", ram=64,
                                                             vcpus=1, disk=5)]

        flavor = self.context._discover_or_create_flavor(64, 5)
        self.assertEqual("id1", flavor.id)
        self.assertEqual(0, len(self.context._created_flavors))

    def test__discover_or_create_flavor(self):
        client = self.context.clients.nova()
        client.flavors.list.return_value = []
        client.flavors.create.side_effect = [fakes.FakeFlavor(id="id1")]

        flavor = self.context._discover_or_create_flavor(64, 5)
        self.assertEqual("id1", flavor.id)
        self.assertEqual("id1", self.context._created_flavors[0].id)

    def test__create_network_resources(self):
        client = self.context.clients.neutron()
        fake_network = {
            "id": "nid1",
            "name": "network",
            "status": "status"}

        client.create_network.side_effect = [{"network": fake_network}]
        client.create_router.side_effect = [{"router": {"id": "rid1"}}]
        client.create_subnet.side_effect = [{"subnet": {"id": "subid1"}}]
        client.list_networks.return_value = {"networks": []}

        network = self.context._create_network_resources()
        self.assertEqual("nid1", network["id"])
        self.assertEqual("nid1", self.context._created_networks[0]["id"])
        self.assertEqual("rid1",
                         self.context._created_networks[0]["router_id"])
        self.assertEqual("subid1",
                         self.context._created_networks[0]["subnets"][0])

    @mock.patch("rally_openstack.wrappers.network.NeutronWrapper.ext_gw_mode_enabled",  # noqa E501
                new_callable=mock.PropertyMock, return_value=True)
    def test__create_network_resources_public_network_override(self, mock_ext_gw_mode_enabled):  # noqa E501
        client = self.context.clients.neutron()
        conf = self.context.conf

        conf.add_section("network")
        conf.set("network", "public_network_id", "my-uuid")

        fake_network = {
            "id": "nid1",
            "name": "network",
            "status": "status"}

        client.create_network.side_effect = [{"network": fake_network}]
        client.create_router.side_effect = [{"router": {"id": "rid1"}}]
        client.create_subnet.side_effect = [{"subnet": {"id": "subid1"}}]
        client.list_networks.return_value = {"networks": []}

        self.context._create_network_resources()
        _name, pos, _kwargs = client.create_router.mock_calls[0]
        router = pos[0]["router"]
        external_gateway_info = router["external_gateway_info"]
        self.assertEqual('my-uuid', external_gateway_info["network_id"])
        self.assertEqual(True, external_gateway_info["enable_snat"])

    def test__cleanup_tempest_roles(self):
        self.context._created_roles = [fakes.FakeRole(), fakes.FakeRole()]

        self.context._cleanup_tempest_roles()
        client = self.context.clients.keystone()
        self.assertEqual(2, client.roles.delete.call_count)

    @mock.patch("rally_openstack.services.image.image.Image")
    def test__cleanup_images(self, mock_image):
        self.context._created_images = [fakes.FakeImage(id="id1"),
                                        fakes.FakeImage(id="id2")]

        self.context.conf.set("compute", "image_ref", "id1")
        self.context.conf.set("compute", "image_ref_alt", "id2")

        image_service = mock_image.return_value
        image_service.get_image.side_effect = [
            fakes.FakeImage(id="id1", status="DELETED"),
            fakes.FakeImage(id="id2"),
            fakes.FakeImage(id="id2", status="DELETED")]

        self.context._cleanup_images()
        client = self.context.clients.glance()
        client.images.delete.assert_has_calls([mock.call("id1"),
                                               mock.call("id2")])

        self.assertEqual("", self.context.conf.get("compute", "image_ref"))
        self.assertEqual("", self.context.conf.get("compute", "image_ref_alt"))

    def test__cleanup_flavors(self):
        self.context._created_flavors = [fakes.FakeFlavor(id="id1"),
                                         fakes.FakeFlavor(id="id2"),
                                         fakes.FakeFlavor(id="id3")]

        self.context.conf.set("compute", "flavor_ref", "id1")
        self.context.conf.set("compute", "flavor_ref_alt", "id2")
        self.context.conf.set("orchestration", "instance_type", "id3")

        self.context._cleanup_flavors()
        client = self.context.clients.nova()
        self.assertEqual(3, client.flavors.delete.call_count)

        self.assertEqual("", self.context.conf.get("compute", "flavor_ref"))
        self.assertEqual("", self.context.conf.get("compute",
                                                   "flavor_ref_alt"))
        self.assertEqual("", self.context.conf.get("orchestration",
                                                   "instance_type"))

    @mock.patch("rally_openstack.wrappers."
                "network.NeutronWrapper.delete_network")
    def test__cleanup_network_resources(
            self, mock_neutron_wrapper_delete_network):
        self.context._created_networks = [{"name": "net-12345"}]
        self.context.conf.set("compute", "fixed_network_name", "net-12345")

        self.context._cleanup_network_resources()
        self.assertEqual(1, mock_neutron_wrapper_delete_network.call_count)
        self.assertEqual("", self.context.conf.get("compute",
                                                   "fixed_network_name"))

    @mock.patch("six.moves.builtins.open", side_effect=mock.mock_open())
    @mock.patch("%s.TempestContext._configure_option" % PATH)
    @mock.patch("%s.TempestContext._create_tempest_roles" % PATH)
    @mock.patch("rally.verification.utils.create_dir")
    def test_setup(self, mock_create_dir,
                   mock__create_tempest_roles, mock__configure_option,
                   mock_open):
        verifier = mock.Mock(deployment=self.deployment)
        verifier.manager.home_dir = "/p/a/t/h"

        # case #1: no neutron and heat
        self.cred.clients.return_value.services.return_value = {}

        ctx = context.TempestContext({"verifier": verifier})
        ctx.conf = mock.Mock()
        ctx.setup()

        ctx.conf.read.assert_called_once_with(verifier.manager.configfile)
        mock_create_dir.assert_called_once_with(ctx.data_dir)
        mock__create_tempest_roles.assert_called_once_with()
        mock_open.assert_called_once_with(verifier.manager.configfile, "w")
        ctx.conf.write(mock_open.side_effect())
        self.assertEqual(
            [mock.call("DEFAULT", "log_file", "/p/a/t/h/tempest.log"),
             mock.call("oslo_concurrency", "lock_path", "/p/a/t/h/lock_files"),
             mock.call("scenario", "img_dir", "/p/a/t/h"),
             mock.call("scenario", "img_file", ctx.image_name,
                       helper_method=ctx._download_image),
             mock.call("compute", "image_ref",
                       helper_method=ctx._discover_or_create_image),
             mock.call("compute", "image_ref_alt",
                       helper_method=ctx._discover_or_create_image),
             mock.call("compute", "flavor_ref",
                       helper_method=ctx._discover_or_create_flavor,
                       flv_ram=config.CONF.openstack.flavor_ref_ram,
                       flv_disk=config.CONF.openstack.flavor_ref_disk),
             mock.call("compute", "flavor_ref_alt",
                       helper_method=ctx._discover_or_create_flavor,
                       flv_ram=config.CONF.openstack.flavor_ref_alt_ram,
                       flv_disk=config.CONF.openstack.flavor_ref_alt_disk)],
            mock__configure_option.call_args_list)

        mock_create_dir.reset_mock()
        mock__create_tempest_roles.reset_mock()
        mock_open.reset_mock()
        mock__configure_option.reset_mock()

        # case #2: neutron and heat are presented
        self.cred.clients.return_value.services.return_value = {
            "network": "neutron", "orchestration": "heat"}

        ctx = context.TempestContext({"verifier": verifier})
        neutron = ctx.clients.neutron()
        neutron.list_networks.return_value = {"networks": ["fake_net"]}
        ctx.conf = mock.Mock()
        ctx.setup()

        ctx.conf.read.assert_called_once_with(verifier.manager.configfile)
        mock_create_dir.assert_called_once_with(ctx.data_dir)
        mock__create_tempest_roles.assert_called_once_with()
        mock_open.assert_called_once_with(verifier.manager.configfile, "w")
        ctx.conf.write(mock_open.side_effect())
        self.assertEqual([
            mock.call("DEFAULT", "log_file", "/p/a/t/h/tempest.log"),
            mock.call("oslo_concurrency", "lock_path", "/p/a/t/h/lock_files"),
            mock.call("scenario", "img_dir", "/p/a/t/h"),
            mock.call("scenario", "img_file", ctx.image_name,
                      helper_method=ctx._download_image),
            mock.call("compute", "image_ref",
                      helper_method=ctx._discover_or_create_image),
            mock.call("compute", "image_ref_alt",
                      helper_method=ctx._discover_or_create_image),
            mock.call("compute", "flavor_ref",
                      helper_method=ctx._discover_or_create_flavor,
                      flv_ram=config.CONF.openstack.flavor_ref_ram,
                      flv_disk=config.CONF.openstack.flavor_ref_disk),
            mock.call("compute", "flavor_ref_alt",
                      helper_method=ctx._discover_or_create_flavor,
                      flv_ram=config.CONF.openstack.flavor_ref_alt_ram,
                      flv_disk=config.CONF.openstack.flavor_ref_alt_disk),
            mock.call("compute", "fixed_network_name",
                      helper_method=ctx._create_network_resources),
            mock.call("orchestration", "instance_type",
                      helper_method=ctx._discover_or_create_flavor,
                      flv_ram=config.CONF.openstack.heat_instance_type_ram,
                      flv_disk=config.CONF.openstack.heat_instance_type_disk)
        ], mock__configure_option.call_args_list)
