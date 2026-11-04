"""The fixed host runner must refuse a translator interface it cannot bind correctly."""
import copy
import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('metal_check',Path(__file__).resolve().parents[1]/'src/graphics/check.py')
check=importlib.util.module_from_spec(spec);spec.loader.exec_module(check)


class MetalLayoutTests(unittest.TestCase):
    def test_rejects_changed_descriptor_push_range_or_entry(self):
        base={'kind':'compute','layout':{'sets':[{'set':0,'bindings':[{'binding':0,'ty':7,'count':1}]}],'push_constants':[{'offset':0,'size':4,'stages':32}]},'stages':[{'entry_point':'main'}]}
        check.check_layout(base)
        for field,value in [('binding',1),('ty',6),('count',2)]:
            data=copy.deepcopy(base);data['layout']['sets'][0]['bindings'][0][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):check.check_layout(data)
        data=copy.deepcopy(base);data['layout']['push_constants'][0]['size']=8
        with self.assertRaises(ValueError):check.check_layout(data)
        data=copy.deepcopy(base);data['stages'][0]['entry_point']='other'
        with self.assertRaises(ValueError):check.check_layout(data)


if __name__=='__main__':unittest.main()
