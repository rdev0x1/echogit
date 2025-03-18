from setuptools import setup, find_packages

setup(
    name='echogit',
    version='0.1.0',
    author='Ramon Dev',
    author_email='ramon.devx@proton.me',
    description='A tool for local synchronization of data using Git',
    long_description=open('README.md').read(),
    long_description_content_type='text/markdown',
    url='https://github.com/rdev0x1/echogit',
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        # List your project's dependencies here, e.g.,
        # 'requests',
    ],
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Natural Language :: English',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.10',
        'Operating System :: OS Independent',
    ],
    entry_points={
        'console_scripts': [
            'echogit=echogit.__main__:main',
        ],
    },
    python_requires='>=3.6',
)
