1) Use a public key to solve the unreachable issue in server-install.yml
2) for conda installation issues increase the EC2 instace to t3.medium
3) server-migrate.sh had issues when the Task : "Create the first data migration". Dealt manually by running the server-migrate.sh script on Target server.
   1) Django installation error : install Django in venv 
   2) Permission issue: login as root
   3) run "pip install -r conf/requirements.txt"
   4) run the script
4) Handling the hosts.ini file: 
   1) getting rid of the file hosts.ini file
   2) since we are using one target add the host into the ansible scripts itself
5) 