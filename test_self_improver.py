#!/usr/bin/env python3
"""Quick test of self_improver plugin"""

from plugins.self_improver.plugin import SelfImproverPlugin

p = SelfImproverPlugin({})
print("✓ Plugin loaded successfully\n")
print("Available capabilities:")
for cap in p.get_capabilities():
    print(f"  • {cap['action']: <25} {cap['description']}")
