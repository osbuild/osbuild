up:
	vagrant up

destroy:
	vagrant destroy -f

install-deps:
	vagrant provision

run-tests-remotely:
	vagrant ssh -c 'pushd /vagrant; sudo python3 run-tests.py'
