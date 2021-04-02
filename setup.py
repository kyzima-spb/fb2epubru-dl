from setuptools import setup


setup(
    name='fb2epubru-dl',
    use_scm_version={
        'relative_to': __file__,
        'local_scheme': lambda version: '',
    },
    description='Command-line program to download books from fb2-epub.ru',
    url='https://github.com/kyzima-spb/fb2epubru-dl',
    license='MIT',
    author='Kirill Vercetti',
    author_email='office@kyzima-spb.com',
    py_modules=['fb2epubru_dl'],
    entry_points={
        'console_scripts': [
            'fb2epubru-dl = fb2epubru_dl:main',
        ],
    },
    include_package_data=True,
    setup_requires=['setuptools_scm'],
    install_requires=[
        'Click>=7.0',
        'requests>=2',
        'lxml>=4',
        'cssselect>=1.1',
    ],
    classifiers=[
        'Operating System :: OS Independent',
        'Programming Language :: Python',
    ]
)
