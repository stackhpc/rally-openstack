# Copyright (C) 2014 Yahoo! Inc. All Rights Reserved.
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

from unittest import mock

from rally import exceptions

from rally_openstack.task import types
from tests.unit import fakes
from tests.unit import test


class OpenStackResourceTypeTestCase(test.TestCase):
    def test__find_resource(self):

        @types.configure(name=self.id())
        class FooType(types.OpenStackResourceType):
            def pre_process(self, resource_spec, config):
                pass

        ftype = FooType({})

        resources = dict(
            (name, fakes.FakeResource(name=name))
            for name in ["Fake1", "Fake2", "Fake3"])
        # case #1: 100% name match
        self.assertEqual(
            resources["Fake2"],
            ftype._find_resource({"name": "Fake2"}, resources.values()))

        # case #2: pick the latest one
        self.assertEqual(
            resources["Fake3"],
            ftype._find_resource({"name": "Fake"}, resources.values()))

        # case #3: regex one match
        self.assertEqual(
            resources["Fake2"],
            ftype._find_resource({"regex": ".ake2"}, resources.values()))

        # case #4: regex, pick the latest one
        self.assertEqual(
            resources["Fake3"],
            ftype._find_resource({"regex": "Fake"}, resources.values()))

    def test__find_resource_negative(self):

        @types.configure(name=self.id())
        class FooType(types.OpenStackResourceType):
            def pre_process(self, resource_spec, config):
                pass

        ftype = FooType({})
        # case #1: the wrong resource spec
        e = self.assertRaises(exceptions.InvalidScenarioArgument,
                              ftype._find_resource, {}, [])
        self.assertIn("'id', 'name', or 'regex' not found",
                      e.format_message())

        # case #2: two matches for one name
        resources = [fakes.FakeResource(name="Fake1"),
                     fakes.FakeResource(name="Fake2"),
                     fakes.FakeResource(name="Fake1")]
        e = self.assertRaises(
            exceptions.InvalidScenarioArgument,
            ftype._find_resource, {"name": "Fake1"}, resources)
        self.assertIn("with name 'Fake1' is ambiguous, possible matches",
                      e.format_message())

        # case #3: no matches at all
        resources = [fakes.FakeResource(name="Fake1"),
                     fakes.FakeResource(name="Fake2"),
                     fakes.FakeResource(name="Fake3")]
        e = self.assertRaises(
            exceptions.InvalidScenarioArgument,
            ftype._find_resource, {"name": "Foo"}, resources)
        self.assertIn("with pattern 'Foo' not found",
                      e.format_message())

        # case #4: two matches for one name, but 'accurate' is True
        resources = [fakes.FakeResource(name="Fake1"),
                     fakes.FakeResource(name="Fake2"),
                     fakes.FakeResource(name="Fake3")]
        e = self.assertRaises(
            exceptions.InvalidScenarioArgument,
            ftype._find_resource, {"name": "Fake", "accurate": True},
            resources)
        self.assertIn("with name 'Fake' not found",
                      e.format_message())

        # case #5: two matches for one name, but 'accurate' is True
        resources = [fakes.FakeResource(name="Fake1"),
                     fakes.FakeResource(name="Fake2"),
                     fakes.FakeResource(name="Fake3")]
        e = self.assertRaises(
            exceptions.InvalidScenarioArgument,
            ftype._find_resource, {"regex": "Fake", "accurate": True},
            resources)
        self.assertIn("with name 'Fake' is ambiguous, possible matches",
                      e.format_message())


class FlavorTestCase(test.TestCase):

    def setUp(self):
        super(FlavorTestCase, self).setUp()
        self.clients = fakes.FakeClients()
        self.clients.nova().flavors._cache(fakes.FakeResource(name="m1.tiny",
                                                              id="1"))
        self.clients.nova().flavors._cache(fakes.FakeResource(name="m1.nano",
                                                              id="42"))
        self.clients.nova().flavors._cache(fakes.FakeResource(name="m1.large",
                                                              id="44"))
        self.clients.nova().flavors._cache(fakes.FakeResource(name="m1.large",
                                                              id="45"))
        self.type_cls = types.Flavor(
            context={"admin": {"credential": mock.Mock()}})
        self.type_cls._clients = self.clients

    def test_preprocess_by_id(self):
        resource_spec = {"id": "42"}
        flavor_id = self.type_cls.pre_process(
            resource_spec=resource_spec, config={})
        self.assertEqual("42", flavor_id)

    def test_preprocess_by_name(self):
        resource_spec = {"name": "m1.nano"}
        flavor_id = self.type_cls.pre_process(
            resource_spec=resource_spec, config={})
        self.assertEqual("42", flavor_id)

    def test_preprocess_by_name_no_match(self):
        resource_spec = {"name": "m1.medium"}
        self.assertRaises(exceptions.InvalidScenarioArgument,
                          self.type_cls.pre_process,
                          resource_spec=resource_spec, config={})

    def test_preprocess_by_name_multiple_match(self):
        resource_spec = {"name": "m1.large"}
        self.assertRaises(exceptions.InvalidScenarioArgument,
                          self.type_cls.pre_process,
                          resource_spec=resource_spec, config={})

    def test_preprocess_by_regex(self):
        resource_spec = {"regex": r"m(1|2)\.nano"}
        flavor_id = self.type_cls.pre_process(
            resource_spec=resource_spec, config={})
        self.assertEqual("42", flavor_id)

    def test_preprocess_by_regex_multiple_match(self):
        resource_spec = {"regex": "^m1"}
        self.assertRaises(exceptions.InvalidScenarioArgument,
                          self.type_cls.pre_process,
                          resource_spec=resource_spec, config={})

    def test_preprocess_by_regex_no_match(self):
        resource_spec = {}
        self.assertRaises(exceptions.InvalidScenarioArgument,
                          self.type_cls.pre_process,
                          resource_spec=resource_spec, config={})


class GlanceImageTestCase(test.TestCase):

    def setUp(self):
        super(GlanceImageTestCase, self).setUp()
        self.clients = fakes.FakeClients()
        image1 = fakes.FakeResource(name="cirros-0.5.2-uec", id="100")
        self.clients.glance().images._cache(image1)
        image2 = fakes.FakeResource(name="cirros-0.5.2-uec-ramdisk", id="101")
        self.clients.glance().images._cache(image2)
        image3 = fakes.FakeResource(name="cirros-0.5.2-uec-ramdisk-copy",
                                    id="102")
        self.clients.glance().images._cache(image3)
        image4 = fakes.FakeResource(name="cirros-0.5.2-uec-ramdisk-copy",
                                    id="103")
        self.clients.glance().images._cache(image4)
        self.type_cls = types.GlanceImage(
            context={"admin": {"credential": mock.Mock()}})
        self.type_cls._clients = self.clients

    def test_preprocess_by_id(self):
        resource_spec = {"id": "100"}
        image_id = self.type_cls.pre_process(
            resource_spec=resource_spec, config={})
        self.assertEqual("100", image_id)

    def test_preprocess_by_name(self):
        resource_spec = {"name": "^cirros-0.5.2-uec$"}
        image_id = self.type_cls.pre_process(
            resource_spec=resource_spec, config={})
        self.assertEqual("100", image_id)

    def test_preprocess_by_name_no_match(self):
        resource_spec = {"name": "cirros-0.5.2-uec-boot"}
        self.assertRaises(exceptions.InvalidScenarioArgument,
                          self.type_cls.pre_process,
                          resource_spec=resource_spec, config={})

    def test_preprocess_by_name_match_multiple(self):
        resource_spec = {"name": "cirros-0.5.2-uec-ramdisk-copy"}
        self.assertRaises(exceptions.InvalidScenarioArgument,
                          self.type_cls.pre_process,
                          resource_spec=resource_spec, config={})

    def test_preprocess_by_regex(self):
        resource_spec = {"regex": "-uec$"}
        image_id = self.type_cls.pre_process(
            resource_spec=resource_spec, config={})
        self.assertEqual("100", image_id)

    def test_preprocess_by_regex_match_multiple(self):
        resource_spec = {"regex": "^cirros"}
        image_id = self.type_cls.pre_process(resource_spec=resource_spec,
                                             config={})
        # matching resources are sorted by the names. It is impossible to
        #   predict which resource will be luckiest
        self.assertIn(image_id, ["102", "103"])

    def test_preprocess_by_regex_no_match(self):
        resource_spec = {"regex": "-boot$"}
        self.assertRaises(exceptions.InvalidScenarioArgument,
                          self.type_cls.pre_process,
                          resource_spec=resource_spec, config={})


class GlanceImageArgsTestCase(test.TestCase):

    def test_preprocess(self):
        self.assertEqual(
            {},
            types.GlanceImageArguments({}).pre_process(
                resource_spec={}, config={}))
        self.assertEqual(
            {"visibility": "public"},
            types.GlanceImageArguments({}).pre_process(
                config={}, resource_spec={"visibility": "public"}))
        self.assertEqual(
            {"visibility": "public"},
            types.GlanceImageArguments({}).pre_process(
                config={}, resource_spec={"visibility": "public",
                                          "is_public": False}))
        self.assertEqual(
            {"visibility": "private"},
            types.GlanceImageArguments({}).pre_process(
                config={}, resource_spec={"is_public": False}))


class EC2ImageTestCase(test.TestCase):

    def setUp(self):
        super(EC2ImageTestCase, self).setUp()
        self.clients = fakes.FakeClients()
        image1 = fakes.FakeResource(name="cirros-0.5.2-uec", id="100")
        self.clients.glance().images._cache(image1)
        image2 = fakes.FakeResource(name="cirros-0.5.2-uec-ramdisk", id="102")
        self.clients.glance().images._cache(image2)
        image3 = fakes.FakeResource(name="cirros-0.5.2-uec-ramdisk-copy",
                                    id="102")
        self.clients.glance().images._cache(image3)
        image4 = fakes.FakeResource(name="cirros-0.5.2-uec-ramdisk-copy",
                                    id="103")
        self.clients.glance().images._cache(image4)

        ec2_image1 = fakes.FakeResource(name="cirros-0.5.2-uec", id="200")
        ec2_image2 = fakes.FakeResource(name="cirros-0.5.2-uec-ramdisk",
                                        id="201")
        ec2_image3 = fakes.FakeResource(name="cirros-0.5.2-uec-ramdisk-copy",
                                        id="202")
        ec2_image4 = fakes.FakeResource(name="cirros-0.5.2-uec-ramdisk-copy",
                                        id="203")

        self.clients.ec2().get_all_images = mock.Mock(
            return_value=[ec2_image1, ec2_image2, ec2_image3, ec2_image4])

        self.type_cls = types.EC2Image(
            context={"admin": {"credential": mock.Mock()}})
        self.type_cls._clients = self.clients

    def test_preprocess_by_name(self):
        resource_spec = {"name": "^cirros-0.5.2-uec$"}
        ec2_image_id = self.type_cls.pre_process(resource_spec=resource_spec,
                                                 config={})
        self.assertEqual("200", ec2_image_id)

    def test_preprocess_by_id(self):
        resource_spec = {"id": "100"}
        ec2_image_id = self.type_cls.pre_process(resource_spec=resource_spec,
                                                 config={})
        self.assertEqual("200", ec2_image_id)

    def test_preprocess_by_id_no_match(self):
        resource_spec = {"id": "101"}
        self.assertRaises(exceptions.InvalidScenarioArgument,
                          self.type_cls.pre_process,
                          resource_spec=resource_spec, config={})

    def test_preprocess_by_name_no_match(self):
        resource_spec = {"name": "cirros-0.5.2-uec-boot"}
        self.assertRaises(exceptions.InvalidScenarioArgument,
                          self.type_cls.pre_process,
                          resource_spec=resource_spec, config={})

    def test_preprocess_by_name_match_multiple(self):
        resource_spec = {"name": "cirros-0.5.2-uec-ramdisk-copy"}
        self.assertRaises(exceptions.InvalidScenarioArgument,
                          self.type_cls.pre_process,
                          resource_spec=resource_spec, config={})

    def test_preprocess_by_regex(self):
        resource_spec = {"regex": "-uec$"}
        ec2_image_id = self.type_cls.pre_process(resource_spec=resource_spec,
                                                 config={})
        self.assertEqual("200", ec2_image_id)

    def test_preprocess_by_regex_match_multiple(self):
        resource_spec = {"regex": "^cirros"}
        self.assertRaises(exceptions.InvalidScenarioArgument,
                          self.type_cls.pre_process,
                          resource_spec=resource_spec, config={})

    def test_preprocess_by_regex_no_match(self):
        resource_spec = {"regex": "-boot$"}
        self.assertRaises(exceptions.InvalidScenarioArgument,
                          self.type_cls.pre_process,
                          resource_spec=resource_spec, config={})


class VolumeTypeTestCase(test.TestCase):

    def setUp(self):
        super(VolumeTypeTestCase, self).setUp()
        cinder = mock.patch("rally_openstack.task.types.block.BlockStorage")
        self.service = cinder.start().return_value
        self.addCleanup(cinder.stop)

        volume_type1 = fakes.FakeResource(name="lvmdriver-1", id=100)

        self.type_cls = types.VolumeType(
            context={"admin": {"credential": mock.Mock()}})
        self.service.list_types.return_value = [volume_type1]

    def test_preprocess_by_id(self):
        resource_spec = {"id": 100}
        volumetype_id = self.type_cls.pre_process(resource_spec=resource_spec,
                                                  config={})
        self.assertEqual(100, volumetype_id)

    def test_preprocess_by_name(self):
        resource_spec = {"name": "lvmdriver-1"}
        volumetype_id = self.type_cls.pre_process(resource_spec=resource_spec,
                                                  config={})
        self.assertEqual(100, volumetype_id)

    def test_preprocess_by_name_no_match(self):
        resource_spec = {"name": "nomatch-1"}
        self.assertRaises(exceptions.InvalidScenarioArgument,
                          self.type_cls.pre_process,
                          resource_spec=resource_spec, config={})

    def test_preprocess_by_regex(self):
        resource_spec = {"regex": "^lvm.*-1"}
        volumetype_id = self.type_cls.pre_process(resource_spec=resource_spec,
                                                  config={})
        self.assertEqual(100, volumetype_id)

    def test_preprocess_by_regex_no_match(self):
        resource_spec = {"regex": "dd"}
        self.assertRaises(exceptions.InvalidScenarioArgument,
                          self.type_cls.pre_process,
                          resource_spec=resource_spec, config={})


class NeutronNetworkTestCase(test.TestCase):

    def setUp(self):
        super(NeutronNetworkTestCase, self).setUp()
        self.clients = fakes.FakeClients()
        net1_data = {"network": {
            "name": "net1"
        }}
        network1 = self.clients.neutron().create_network(net1_data)
        self.net1_id = network1["network"]["id"]
        self.type_cls = types.NeutronNetwork(
            context={"admin": {"credential": mock.Mock()}})
        self.type_cls._clients = self.clients

    def test_preprocess_by_id(self):
        resource_spec = {"id": self.net1_id}
        network_id = self.type_cls.pre_process(resource_spec=resource_spec,
                                               config={})
        self.assertEqual(network_id, self.net1_id)

    def test_preprocess_by_name(self):
        resource_spec = {"name": "net1"}
        network_id = self.type_cls.pre_process(resource_spec=resource_spec,
                                               config={})
        self.assertEqual(network_id, self.net1_id)

    def test_preprocess_by_name_no_match(self):
        resource_spec = {"name": "nomatch-1"}
        self.assertRaises(exceptions.InvalidScenarioArgument,
                          self.type_cls.pre_process,
                          resource_spec=resource_spec, config={})


class WatcherStrategyTestCase(test.TestCase):

    def setUp(self):
        super(WatcherStrategyTestCase, self).setUp()
        self.clients = fakes.FakeClients()
        self.strategy = self.clients.watcher().strategy._cache(
            fakes.FakeResource(name="dummy", id="1"))

        self.type_cls = types.WatcherStrategy(
            context={"admin": {"credential": mock.Mock()}})
        self.type_cls._clients = self.clients

    def test_preprocess_by_name(self):
        resource_spec = {"name": "dummy"}
        strategy_id = self.type_cls.pre_process(resource_spec=resource_spec,
                                                config={})
        self.assertEqual(self.strategy.uuid, strategy_id)

    def test_preprocess_by_name_no_match(self):
        resource_spec = {"name": "dummy-1"}
        self.assertRaises(exceptions.RallyException,
                          self.type_cls.pre_process,
                          resource_spec=resource_spec, config={})


class WatcherGoalTestCase(test.TestCase):

    def setUp(self):
        super(WatcherGoalTestCase, self).setUp()
        self.clients = fakes.FakeClients()
        self.goal = self.clients.watcher().goal._cache(
            fakes.FakeResource(name="dummy", id="1"))
        self.type_cls = types.WatcherGoal(
            context={"admin": {"credential": mock.Mock()}})
        self.type_cls._clients = self.clients

    def test_preprocess_by_name(self):
        resource_spec = {"name": "dummy"}
        goal_id = self.type_cls.pre_process(resource_spec=resource_spec,
                                            config={})
        self.assertEqual(self.goal.uuid, goal_id)

    def test_preprocess_by_name_no_match(self):
        resource_spec = {"name": "dummy-1"}
        self.assertRaises(exceptions.RallyException,
                          self.type_cls.pre_process,
                          resource_spec=resource_spec, config={})
