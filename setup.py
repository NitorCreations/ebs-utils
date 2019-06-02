# Copyright 2019 Nitor Creations Oy
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import sys
from setuptools import setup
from ec2_utils import CONSOLESCRIPTS

setup(name='ec2_utils',
      version='0.1',
      description='Tools for using on an ec2 instance',
      url='http://github.com/NitorCreations/ec2-utils',
      download_url='https://github.com/NitorCreations/ec2-utils/tarball/0.1',
      author='Pasi Niemi',
      author_email='pasi@nitor.com',
      license='Apache 2.0',
      packages=['ec2_utils'],
      include_package_data=True,
      entry_points={
          'console_scripts': CONSOLESCRIPTS,
      },
      setup_requires=[
          'pytest-runner'
      ],
      install_requires=[
          'future',
          'boto3',
          'awscli',
          'requests',
          'termcolor',
          'argcomplete',
          'psutil',
          'python-dateutil',
          'retry'
      ] + ([
          'win-unicode-console',
          'wmi',
          'pypiwin32'
          ] if sys.platform.startswith('win') else []),
      tests_require=[
          'pytest',
          'pytest-mock',
          'pytest-cov',
          'coverage',
          'coveralls'
      ],
      zip_safe=False)
