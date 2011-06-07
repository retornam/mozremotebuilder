from setuptools import setup, find_packages

desc = """Bisect on changesets and call remote builder for Mozilla Firefox / moz-central repository"""
summ = """Interactive regression finder on moz-central for Firefox"""

setup(name="mozremotebuilder",
      version="0.1.0",
      description=desc,
      long_description=summ,
      author='Sam Liu',
      author_email='sam@ambushnetworks.com',
      url='http://github.com/samliu/mozremotebuilder',
      license='MPL 1.1/GPL 2.0/LGPL 2.1',
      packages=find_packages(exclude=['legacy']),
      entry_points="""
          [console_scripts]
          mozremotebuild = mozremotebuilder:callercli
        """,
      platforms =['Any'],
      install_requires = ['httplib2 >= 0.6.0', 'mozrunner >= 2.5.1'],
      classifiers=['Development Status :: 4 - Beta',
                   'Environment :: Console',
                   'Intended Audience :: Developers',
                   'Operating System :: OS Independent'
                  ]
     )
