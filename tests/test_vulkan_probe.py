"""Exercise the real shared Vulkan core and bounded fence fault handling on host Lavapipe."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
ICD = Path('/usr/share/vulkan/icd.d/lvp_icd.x86_64.json')


class VulkanProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which('c++') or not Path('/usr/include/vulkan/vulkan.h').is_file() or not ICD.is_file():
            raise unittest.SkipTest('Host Vulkan compiler/headers/Lavapipe are not installed')
        cls.temp = tempfile.TemporaryDirectory()
        cls.directory = Path(cls.temp.name)
        cls.binary = cls.directory / 'probe'
        cls.env = {**os.environ, 'VK_ICD_FILENAMES': str(ICD)}
        command = ['c++', '-std=c++17', '-O2', '-Wno-missing-field-initializers', str(ROOT/'src/android-probe/native/probe.cpp'), str(ROOT/'src/android-probe/native/host.cpp'), '-lvulkan', '-pthread', '-o', str(cls.binary)]
        build = subprocess.run(command, capture_output=True, text=True, timeout=45)
        if build.returncode: raise AssertionError(build.stderr)
        # Simulate a kernel/driver fence that never completes without hanging hardware.
        source = cls.directory / 'timeout.cpp'
        source.write_text('#include <vulkan/vulkan.h>\n#include <thread>\n#include <chrono>\nextern "C" VKAPI_ATTR VkResult VKAPI_CALL vkWaitForFences(VkDevice,uint32_t,const VkFence*,VkBool32,uint64_t){std::this_thread::sleep_for(std::chrono::milliseconds(5));return VK_TIMEOUT;}\n')
        cls.inject = cls.directory / 'timeout.so'
        build = subprocess.run(['c++','-shared','-fPIC',str(source),'-pthread','-o',str(cls.inject)],capture_output=True,text=True,timeout=20)
        if build.returncode: raise AssertionError(build.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def run_probe(self, *args, env=None):
        run = subprocess.run([str(self.binary), *args], capture_output=True, text=True, env=env or self.env, timeout=12)
        return run, json.loads(run.stdout)

    def test_exact_pixels_from_actual_host_vulkan(self):
        run, data = self.run_probe()
        self.assertEqual(run.returncode, 0, run.stderr + run.stdout)
        self.assertEqual((data['outcome'], data['compared_pixels'], data['mismatched_pixels']), ('pass',65536,0))
        self.assertFalse(data['requires_process_restart'])

    def test_stop_before_start_submits_no_pixels(self):
        run, data = self.run_probe('--cancel')
        self.assertEqual(run.returncode, 0)
        self.assertEqual(data['outcome'], 'cancelled')
        self.assertEqual(data['compared_pixels'], 0)

    def test_timeout_retains_in_flight_resources_and_requires_restart(self):
        run, data = self.run_probe(env={**self.env,'LD_PRELOAD':str(self.inject)})
        self.assertEqual(run.returncode, 1)
        self.assertEqual(data['outcome'], 'fail')
        self.assertIn('deadline', data['error'])
        self.assertTrue(data['requires_process_restart'])
        self.assertEqual(data['compared_pixels'],0)
        self.assertLess(data['elapsed_ms'],6000)


if __name__ == '__main__':
    unittest.main()
