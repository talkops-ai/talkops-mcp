# Copyright (C) 2025 StructBinary
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

_loader_registry = {}

def register_loader(key_or_cls, cls=None):
    """
    Register a loader class. Can be used as a decorator or with explicit key.
    Usage:
      @register_loader
      class MyLoader: ...
    or
      register_loader("my_key", MyLoader)
    """
    if cls is None:
        # Used as a decorator
        _loader_registry[key_or_cls.__name__] = key_or_cls
        return key_or_cls
    else:
        # Used with explicit key
        _loader_registry[key_or_cls] = cls

def get_loader(file_type: str):
    """
    Retrieve a loader class by file type/extension.
    """
    return _loader_registry.get(file_type) 