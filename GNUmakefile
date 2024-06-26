#
# GNU 'make' file
#

# PY[23] is the target Python interpreter.  It must have pytest installed.
# The python2 assumes a Nix supplied python2, and that all Python2 "pip"
# modules have been installed locally.  To test Python2, install Nix and try:
#
#     make nix-install2
#     make nix-test2
#
PY2		?= PIP_USER=1 PYTHONPATH=~/.local/lib/python2.7/site-packages/ python2
PY3		?= python3

TZ		?= Canada/Mountain

VERSION		= $(shell $(PY3) -c 'exec(open("crypto_licensing/version.py").read()); print( __version__ )')

GIT_SSH_COMMAND	= ssh -o StrictHostKeyChecking=no
export GIT_SSH_COMMAND

GHUB_NAME	= crypto-licensing
GHUB_REPO	= git@github.com:pjkundert/$(GHUB_NAME).git
GHUB_BRCH	= $(shell git rev-parse --abbrev-ref HEAD )

# We'll agonizingly find the directory above this makefile's path
VENV_DIR	= $(abspath $(dir $(abspath $(lastword $(MAKEFILE_LIST))))/.. )
VENV_NAME	= $(GHUB_NAME)-$(VERSION)
VENV		= $(VENV_DIR)/$(VENV_NAME)
VENV_OPTS	=

# To see all pytest output, uncomment --capture=no ...
PYTESTOPTS	= # --capture=no # --log-cli-level=25 # INFO  # DEBUG # 23 == DETAIL # 25 == NORMAL

PY3TEST		= TZ=$(TZ) $(PY3) -m pytest $(PYTESTOPTS)
PY2TEST		= TZ=$(TZ) $(PY2) -m pytest $(PYTESTOPTS)

.PHONY: all test clean build install upload wheel FORCE
all:			help

help:
	@echo "GNUmakefile for crypto-licensing.  Targets:"
	@echo "  help			This help"
	@echo "  test			Run unit tests under Python3"
	@echo "  build			Build Python3 / PyPi artifacts"
	@echo "  install		Install in /usr/local for Python3"
	@echo "  upload			Upload new version to pypi (package maintainer only)"
	@echo "  clean			Remove build artifacts"

#
# nix-...:
#
# Use a NixOS environment to execute the make target, eg.
#
#     nix-venv-activate
#
#     The default is the Python 3 crypto_licensing target in default.nix; choose
# TARGET=crypto_licensing_py2 to test under Python 2 (more difficult as time goes on).
#
nix-%:
	nix-shell --pure --run "make $*"

#
# test...:	Perform Unit Tests
#
#     Assumes that the requirements.txt has been installed in the target Python environment.  This
# is probably best accomplished by first creating/activating a venv, and then running the test:
#
#     $ make nix-venv-activate
#     (crypto-licensing-4.0.0) [perry@Perrys-MBP crypto-licensing (feature-py-3.12)]$ make test
#     make[1]: Entering directory '/Users/perry/src/crypto-licensing'
#     ...
#
test:				test3
test2:
	$(PY2TEST)
test3:
	$(PY3TEST)
test23:				test2 test3


doctest:
	$(PY3TEST) --doctest-modules


analyze:
	$(PY3) -m flake8 --color never -j 1 --max-line-length=200 \
	  --ignore=W503,E201,E202,E127,E221,E222,E223,E226,E231,E241,E242,E251,E265,E272,E274,E275 \
	  --extend-exclude="ed25519_djb.py,djbec.py,__init__.py" \
	  crypto_licensing

pylint:
	cd .. && pylint crypto_licensing --disable=W,C,R

#
# venv:		Create a Virtual Env containing the installed repo
#
.PHONY: venv venv-activate.sh venv-activate
venv:			$(VENV)
venv-activate.sh:	$(VENV)/venv-activate.sh
venv-activate:		$(VENV)/venv-activate.sh
	@echo; echo "*** Activating $< VirtualEnv for Interactive $(SHELL)"
	@bash --init-file $< -i

$(VENV):
	@git diff --quiet || ( \
	    echo -e "\n\n!!! Git repo branch $(GHUB_BRCH) is dirty; cannot create venv!"; false \
	)
	@echo; echo "*** Building $@ VirtualEnv..."
	@rm -rf $@ && $(PY3) -m venv $(VENV_OPTS) $@ \
	    && cd $@ && git clone $(GHUB_REPO) -b $(GHUB_BRCH) \
	    && . ./bin/activate \
	    && make -C $(GHUB_NAME) install-dev install

# Activate a given VirtualEnv, and go to its routeros_ssh installation
# o Creates a custom venv-activate.sh script in the venv, and uses it start
#   start a sub-shell in that venv, with a CWD in the contained routeros_ssh installation
$(VENV)/venv-activate.sh: $(VENV)
	( \
	    echo "PS1='[\u@\h \W)]\\$$ '";	\
	    echo "[ ! -r ~/.git-completion.bash ] || source ~/.git-completion.bash"; \
	    echo "[ ! -r ~/.git-prompt.sh ] || source ~/.git-prompt.sh && PS1='[\u@\h \W\$$(__git_ps1 \" (%s)\")]\\$$ '"; \
	    echo "source $</bin/activate";	\
	) > $@


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

export CRYPTO_LIC_PASSWORD
export CRYPTO_LIC_USERNAME

# PRODUCT		= "Awesome Product"
# SERVICE		= "awesome-product"
# CLIENT		= "Someone Special"
# USERNAME	= "someone@example.com"
# PASSWORD	= "password"

products:			end-user			\
				cpppo-test			\
				crypto-licensing		\
				crypto-licensing-server

test-server:			products
	rm licensing.db; $(PY3) -m crypto_licensing.licensing -vvvv --no-gui --username=a@b.c --password=password --config crypto_licensing/licensing


#
# An Agent ID we can use as an End User.  This is the Agent ID to which the final License is issued.
# Make it available under the "<basename>.crypto-keypair-..." of any service wanting to issue
# end-user Licenses to run using this Agent ID, eg. a Crypto Licensing Server.  This is the password
# required at runtime by the server; it will dynamically issue a License to itself (and its
# machine-id), from the crypto-licensing-server.crypto-license issued to this public key.
#
end-user:			USERNAME=a@b.c
end-user:			CRYPTO_LIC_PASSWORD=password
end-user:			$(CREDENTIALS)/end-user.crypto-keypair
	ln -fs $< $(CREDENTIALS)/crypto-licensing-server.crypto-keypair-end-user


GLOBAL_OPTIONS	= -vv
cpppo-test:			AUTHOR="Dominion R&D Corp."
cpppo-test:			DOMAIN=dominionrnd.com
cpppo-test:			PRODUCT="Cpppo Test"
cpppo-test:			SERVICE="cpppo-test"
cpppo-test:			USERNAME=perry@dominionrnd.com
cpppo-test:			CRYPTO_LIC_PASSWORD=$(shell cat ~/.crypto-licensing/cpppo-test.crypto-password )
cpppo-test:			CLIENT="End User"
cpppo-test:			CLIENT_PUBKEY="Yhb9q2B4/fX0Ppt7onaJWwcxdgrEw6WrqoX4Bkfpe6k="
cpppo-test:			GRANTS="{\"cpppo-test\": { \"Hz\": 1000 }}"
cpppo-test:			$(CREDENTIALS)/cpppo-test.crypto-license

#
# The "bootstrap" crypto-licensing License.  Allows a user to obtain a Grant of capabilities to use the
# Python crypto-licensing module in various ways.  This is a core Dominion R&D license, and requires
# access to the Dominion R&D "crypto-licensing.crypto-keypair to issue -- matching the keypair
# identified in Dominon R&D DNS "DKIM" record:
#
#     $ dig +short  crypto-licensing.crypto-licensing._domainkey.dominionrnd.com TXT
#     "v=DKIM1; k=ed25519; p=5cijeUNWyR1mvbIJpqNmUJ6V4Od7vPEgVWOEjxiim8w="
#
# Typically, these kinds of Licenses would be issued to clients by the Dominion crypto-licensing
# server at https://crypto-licensing.dominionrnd.com, but the first one, required to "bootstrap" the
# first crypto-licensing server, must be created manually.
#
crypto-licensing:		AUTHOR="Dominion R&D Corp."
crypto-licensing:		DOMAIN=dominionrnd.com
crypto-licensing:		PRODUCT="Crypto Licensing"
crypto-licensing:		SERVICE="crypto-licensing"
crypto-licensing:		USERNAME=perry@dominionrnd.com
crypto-licensing:		CRYPTO_LIC_PASSWORD=$(shell cat ~/.crypto-licensing/crypto-licensing.crypto-password )
crypto-licensing:		CLIENT=$(AUTHOR)
crypto-licensing:		CLIENT_PUBKEY="8pF7T3nbMAXyf85doRcWqbj8nuJL2QhFdGesLdnFL/8="
crypto-licensing:		GRANTS="{\"crypto-licensing\": {\
    \"fees\": { \
        \"rate\": \"1%\", \
        \"crypto\": { \
            \"ETH\": \"0xe4909b66FD66DA7d86114695A1256418580C8767\", \
            \"BTC\": \"bc1qygm3dlynmjxuflghr0hmq6r7wmff2jd5gtgz0q\" \
        }\
    }\
}}"
crypto-licensing:		$(CREDENTIALS)/crypto-licensing.crypto-license


# The end-user License to run the Crypto Licensing Server
crypto-licensing-server:	AUTHOR="Dominion R&D Corp."
crypto-licensing-server:	DOMAIN=dominionrnd.com
crypto-licensing-server:	PRODUCT="Crypto Licensing Server"
crypto-licensing-server:	SERVICE="crypto-licensing-server"
crypto-licensing-server:	USERNAME=perry@dominionrnd.com
crypto-licensing-server:	CRYPTO_LIC_PASSWORD=$(shell cat ~/.crypto-licensing/crypto-licensing-server.crypto-password )
crypto-licensing-server:	CLIENT="End User"
crypto-licensing-server:	CLIENT_PUBKEY="fzbBlsjV5UQl2vF/89cQMizbWrQDOaN+PciMQnGIUNg="  # end-user.crypto-keypair
crypto-licensing-server:	LICENSE_OPTIONS=--dependency $(CREDENTIALS)/crypto-licensing.crypto-license # --no-confirm
crypto-licensing-server:	GRANTS="{\"crypto-licensing-server\": {\
    \"override\": { \
        \"rate\": \"0.1%\", \
        \"crypto\": { \
            \"ETH\": \"0xe4909b66FD66DA7d86114695A1256418580C8767\", \
            \"BTC\": \"bc1qygm3dlynmjxuflghr0hmq6r7wmff2jd5gtgz0q\" \
        }\
    }\
}}"
crypto-licensing-server:	crypto-licensing $(CREDENTIALS)/crypto-licensing-server.crypto-license


# Preserve all "secondary" intermediate files (eg. the .crypto-keypair generated)
.SECONDARY:

# Create .crypto-keypair from seed; note: if the make rule fails, intermediate files are deleted.
# We expect any password to be transmitted in CRYPTO_LIC_PASSWORD env. var.  If the target name is
# an absolute path, no config-path searching will be done.  Otherwise, we'll save in the
# most-specific writable location (instead of the default most-general).
%.crypto-keypair: %.crypto-seed
	$(PY3) -m crypto_licensing $(GLOBAL_OPTIONS)		\
	    --name $(basename $@ )				\
	    --reverse-save $(KEYPAIR_EXTRA)			\
	    registered						\
	    --username $(USERNAME)				\
	    --seed $$( cat $< ) $(KEYPAIR_OPTIONS)

# Create .crypto-license, signed by .crypto-keypair
%.crypto-license: %.crypto-keypair
	$(PY3) -m crypto_licensing $(GLOBAL_OPTIONS)		\
	    --name $(basename $@ )				\
	    --reverse-save $(KEYPAIR_EXTRA)			\
	   license						\
	    --username $(USERNAME) --no-registering		\
	    --client $(CLIENT) --client-pubkey $(CLIENT_PUBKEY)	\
	    --grant $(GRANTS)					\
	    --author $(AUTHOR) --domain $(DOMAIN) --product $(PRODUCT) $(LICENSE_OPTIONS)

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

PYS		= $(shell find crypto_licensing -name '*.py' -and -not -name '*_test.py' )
TXT		= $(patsubst %.org,%.txt,$(wildcard crypto_licensing/licensing/static/txt/*.org))

# Any build dependencies that are dynamically generated, and may need updating from time to time
deps:		$(TXT)

#
# Python installation artifacts
#
WHEEL		= dist/crypto_licensing-$(VERSION)-py3-none-any.whl

$(WHEEL):	$(TXT) $(PYS) install-dev
	$(PY3) -m build
	@ls -last dist

.PHONY: wheel build2 build23 build install2 install3 install23 install install-dev
wheel:		$(WHEEL)

build3:		wheel

build23:	build3

build: 		build3


install2:
	$(PY2) setup.py install

install3:	$(WHEEL) FORCE
	$(PY3) -m pip install --force-reinstall $<

install23:	install2 install3

install:	install3

install-dev:
	$(PY3) -m pip install --upgrade -r requirements-dev.txt

install-tests:
	$(PY3) -m pip install --upgrade -r requirements-tests.txt


# Support uploading a new version of slip32 to pypi.  Must:
#   o advance __version__ number in slip32/version.py
#   o log in to your pypi account (ie. for package maintainer only)

upload-check: FORCE
	@$(PY3) -m twine --version \
	    || ( echo -e "\n\n*** Missing Python modules; run:\n\n        $(PY3) -m pip install --upgrade twine\n" \
	        && false )

upload: 	upload-check wheel
	$(PY3) -m twine upload --repository pypi dist/crypto_licensing-$(VERSION)*

clean:
	@rm -rf MANIFEST *.png build dist auto *.egg-info $(shell find . -name '*.pyc' -o -name '__pycache__' )


# Run only tests with a prefix containing the target string, eg test-blah
unit-%: unit3-%
unit2-%:
	$(PY2TEST) -k $*
	@echo "unit2-$*: Python 2 Tests completed"
unit3-%:
	$(PY3TEST) -k $*
	@echo "unit2-$*: Python 3 Tests completed"
unit23-%: unit2-% unit3-%


#
# Target to allow the printing of 'make' variables, eg:
#
#     make print-CXXFLAGS
#
print-%:
	@echo $* = "'$($*)'"
	@echo $*\'s origin is $(origin $*)
