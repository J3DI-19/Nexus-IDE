# backend/context_engine/adapters/__init__.py
from .registry import registry
from .languages.python_adapter import PythonAdapter
from .languages.typescript_adapter import TypeScriptAdapter
from .languages.javascript_adapter import JavaScriptAdapter
from .languages.java_adapter import JavaAdapter
from .languages.kotlin_adapter import KotlinAdapter
from .languages.csharp_adapter import CSharpAdapter
from .languages.cpp_adapter import CppAdapter
from .languages.html_adapter import HTMLAdapter
from .languages.css_adapter import CSSAdapter
from .languages.xml_adapter import XMLAdapter
from .languages.json_adapter import JSONAdapter
from .languages.yaml_adapter import YAMLAdapter
from .languages.toml_adapter import TOMLAdapter
from .frameworks.fastapi_adapter import FastAPIAdapter
from .frameworks.react_adapter import ReactAdapter
from .frameworks.android_adapter import AndroidAdapter

# Auto-register core adapters
registry.register_language_adapter(PythonAdapter())
registry.register_language_adapter(TypeScriptAdapter())
registry.register_language_adapter(JavaScriptAdapter())
registry.register_language_adapter(JavaAdapter())
registry.register_language_adapter(KotlinAdapter())
registry.register_language_adapter(CSharpAdapter())
registry.register_language_adapter(CppAdapter())
registry.register_language_adapter(HTMLAdapter())
registry.register_language_adapter(CSSAdapter())
registry.register_language_adapter(XMLAdapter())
registry.register_language_adapter(JSONAdapter())
registry.register_language_adapter(YAMLAdapter())
registry.register_language_adapter(TOMLAdapter())
registry.register_framework_adapter(FastAPIAdapter())
registry.register_framework_adapter(ReactAdapter())
registry.register_framework_adapter(AndroidAdapter())
