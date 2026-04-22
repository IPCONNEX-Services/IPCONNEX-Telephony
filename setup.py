from setuptools import setup, find_packages

with open("requirements.txt") as f:
    install_requires = f.read().strip().split("\n")

setup(
    name="ipconnex_telephony",
    version="0.1.0",
    description="SIP/VoIP billing module for ERPNext — ACR scraping, invoicing, gain dashboards",
    author="IPCONNEX",
    author_email="yacine.g@ipconnex.com",
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=install_requires,
)
