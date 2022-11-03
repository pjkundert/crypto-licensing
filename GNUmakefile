#
# GNU 'make' file
# 

# PY[23] is the target Python interpreter.  It must have pytest installed.
PY		?= python
PY2		?= python2
PY3		?= python3

TZ		?= Canada/Mountain

VERSION		= $(shell $(PY3) -c 'exec(open("crypto_licensing/version.py").read()); print( __version__ )')

# To see all pytest output, uncomment --capture=no ...
PYTESTOPTS	= -vv  --capture=no --log-cli-level=25 # DEBUG # 23 == DETAIL # 25 == NORMAL

PY_TEST		= TZ=$(TZ) $(PY)  -m pytest $(PYTESTOPTS)
PY3TEST		= TZ=$(TZ) $(PY3) -m pytest $(PYTESTOPTS)
PY2TEST		= TZ=$(TZ) $(PY2) -m pytest $(PYTESTOPTS)

.PHONY: all test clean build install upload
all:			help

help:
	@echo "GNUmakefile for crypto-licensing.  Targets:"
	@echo "  help			This help"
	@echo "  test			Run unit tests under Python3"
	@echo "  build			Build Python3 / PyPi artifacts"
	@echo "  install		Install in /usr/local for Python3"
	@echo "  upload			Upload new version to pypi (package maintainer only)"
	@echo "  clean			Remove build artifacts"


test:
	$(PY_TEST)
test2:
	$(PY2TEST)
test3:
	$(PY3TEST)
test23:	test3 test2


doctest:
	$(PY3TEST) --doctest-modules


analyze:
	flake8 -j 1 --max-line-length=200 \
	  --ignore=W503,E201,E202,E127,E221,E222,E223,E226,E231,E241,E242,E251,E265,E272,E274,E275 \
	  --extend-exclude="ed25519_djb.py,djbec.py,__init__.py" \
	  crypto_licensing

pylint:
	cd .. && pylint crypto_licensing --disable=W,C,R



# 
# Bootstrap a License for a product, and a sub-License issue to an end-user of that product
#
# The holder of a Keypair w/ a Private Key '.sk' corresponding to public key in the domain's DKIM
# record, may issue any License they wish for any product with a matching service name, containing
# any Grant keys it wants.  But only the Grant key matching the domain's DKIM record's service name
# will pass verification.  Any other Grant keys are generally refinements of an License
# dependencies' Grants.
# 
#
CREDENTIALS	= $(abspath $(HOME)/.crypto-licensing )
PRODUCT		= "Crypto Licensing Server"
CLIENT		= "Someone Special"
USERNAME	= "someone@example.com"
PASSWORD	= "-"

$(CREDENTIALS)/%.crypto-keypair:	$(CREDENTIALS)/%.crypto-seed
	$(PY3) -m crypto_licensing -vvv register \
	    --username $(USERNAME) --password $(PASSWORD) \
	    --name $(notdir $(basename $@ )) \
	    --seed $$( cat $< )


~/.crypto-licensing/crypto-licensing-server.crypto-keypair \
~/.crypto-licensing/crypto-licensing-server.crypto-license:	~/.crypto-licensing/crypto-licensing-server.crypto-seed

# 
# Build, including org-mode products.
#
#     build-deps:  All of the ...static/txt/.txt files needed to built, before the sdist, wheel or app
# 
%.txt:		%.org
	emacs --batch \
            --eval "(require 'org)" \
            --insert "$<" \
	    --eval "(org-ascii-export-as-ascii nil nil nil nil '(:ascii-charset utf-8))" \
            --eval "(write-file \"$@\")" \
            --kill

TXT		= $(patsubst %.org,%.txt,$(wildcard crypto_licensing/licensing/static/txt/*.org))

# Any build dependencies that are dynamically generated, and may need updating from time to time
deps:		$(TXT)

# 
# Python installation artifacts
#
WHEEL		= dist/crypto_licensing-$(VERSION)-py3-none-any.whl

$(WHEEL):	$(TXT)
	@$(PY3) -m build --version \
	    || ( echo "\n*** Missing Python modules; run:\n\n        $(PY3) -m pip install --upgrade pip setuptools build\n" \
	        && false )
	$(PY3) -m build
	@ls -last dist

wheel:		$(WHEEL)

build3:		wheel

build23:	build3

build: 		build3


install2:
	$(PY2) setup.py install

install3:	$(WHEEL)
	$(PY3) -m pip install --force-reinstall $^

install23:	install2 install3

install:	install3


# Support uploading a new version of slip32 to pypi.  Must:
#   o advance __version__ number in slip32/version.py
#   o log in to your pypi account (ie. for package maintainer only)

upload: 	build
	$(PY3) -m twine upload --repository pypi dist/*

clean:
	@rm -rf MANIFEST *.png build dist auto *.egg-info $(shell find . -name '*.pyc' -o -name '__pycache__' )


# Run only tests with a prefix containing the target string, eg test-blah
unit-%:
	$(PY_TEST) -k $*
unit2-%:
	$(PY2TEST) -k $*
unit3-%:
	$(PY3TEST) -k $*
unit23-%:
	$(PY2TEST) -k $*
	$(PY3TEST) -k $*

#
# Target to allow the printing of 'make' variables, eg:
#
#     make print-CXXFLAGS
#
print-%:
	@echo $* = "'$($*)'"
	@echo $*\'s origin is $(origin $*)
