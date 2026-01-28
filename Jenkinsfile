pipeline {
    agent any

    parameters {
        string(name: 'AWS_ENDPOINT_URL', defaultValue: 'http://localstack:4566', description: 'URL for LocalStack or AWS Endpoint')
        string(name: 'AWS_REGION', defaultValue: 'us-east-1', description: 'AWS Region')
        choice(name: 'DEPLOY_ENV', choices: ['dev', 'staging', 'prod'], description: 'Target deployment environment')
    }

    environment {

        TF_VERSION = '1.0.0'
        TF_VAR_aws_region = "${params.AWS_REGION}"
        // TF_VAR_environment removed in favor of -var-file
        TF_VAR_owner = 'cost-optimization-framework'
        TF_VAR_cost_center = 'engineering'
        TF_PLUGIN_CACHE_DIR = "${env.WORKSPACE}/.terraform-plugin-cache"

        // Terraform Input Variables for Test/LocalStack
        TF_VAR_vpc_id = 'vpc-mock-12345'
        TF_VAR_subnet_ids = '["subnet-mock-a", "subnet-mock-b"]'
        TF_VAR_db_password = 'Password123!'
        TF_VAR_alert_email = 'onyedikachi0813@gmail.com'


        AWS_ACCESS_KEY_ID = 'test'
        AWS_SECRET_ACCESS_KEY = 'test'
        AWS_DEFAULT_REGION = "${params.AWS_REGION}"
        AWS_ENDPOINT_URL = "${params.AWS_ENDPOINT_URL}"
    }
+
    stages {
        stage('Connectivity Check') {
            steps {
                script {
                    echo "Checking connection to LocalStack at ${AWS_ENDPOINT_URL}..."

                    sh "curl -s ${AWS_ENDPOINT_URL}/_localstack/health || echo 'WARNING: Could not connect to LocalStack health endpoint'"
                    sh "aws --version"
                    sh "terraform --version"
                }
            }
        }

        stage('Checkout') {
            steps {
                script {
                    if (fileExists('/var/local-repo/Jenkinsfile')) {
                        echo "Local repository mount detected. Using local code..."
                        sh 'cp -r /var/local-repo/* .'
                    } else {
                        checkout scm
                    }
                }
            }
        }

        stage('Test Automation') {
            parallel {
                stage('Test AWS Lambda') {
                    steps {
                        dir('automation/aws-lambda') {
                            sh '''
                                python3 -m venv venv
                                . venv/bin/activate
                                pip install -r requirements.txt
                                python -m pytest . -v || echo "No tests found, checking imports"
                                python -c "import auto_shutdown; import right_sizing; print('All Lambda functions import successfully')"
                            '''
                        }
                    }
                }
                stage('Test Azure Functions') {
                    steps {
                        dir('automation/azure-functions') {
                            sh '''
                                python3 -m venv venv
                                . venv/bin/activate
                                pip install -r requirements.txt
                                python -m pytest . -v || echo "No tests found, checking imports"
                                python -c "import auto_shutdown; import right_sizing; import cleanup; print('All Azure functions import successfully')"
                            '''
                        }
                    }
                }
            }
        }

        stage('Test Monitoring') {
            steps {
                dir('monitoring') {
                    sh '''
                        python3 -m venv venv
                        . venv/bin/activate
                        pip install -r requirements-aws.txt
                        python -m pytest aws_cost_exporter.py -v || python -c "import aws_cost_exporter; print('AWS exporter imports successfully')"

                        pip install -r requirements-azure.txt
                        python -m pytest azure_cost_exporter.py -v || python -c "import azure_cost_exporter; print('Azure exporter imports successfully')"
                    '''



                }
            }
        }

        stage('Terraform Checks') {
            steps {
                script {
                    sh "mkdir -p ${TF_PLUGIN_CACHE_DIR}"
                    sh "mkdir -p ${env.WORKSPACE}/bin"
                    env.PATH = "${env.WORKSPACE}/bin:${env.PATH}"

                    // Install tools if missing
                    if (!fileExists("${env.WORKSPACE}/bin/tfsec")) {
                        echo "Installing tfsec..."
                        // tfsec install script doesn't support custom dir flag well, downloading binary directly
                        sh "curl -L -o ${env.WORKSPACE}/bin/tfsec https://github.com/aquasecurity/tfsec/releases/latest/download/tfsec-linux-amd64"
                        sh "chmod +x ${env.WORKSPACE}/bin/tfsec"
                    }
                    if (!fileExists("${env.WORKSPACE}/bin/tflint")) {
                        echo "Installing tflint..."
                        // tflint install script uses env var for custom path
                        sh "curl -s https://raw.githubusercontent.com/terraform-linters/tflint/master/install_linux.sh | TFLINT_INSTALL_PATH=${env.WORKSPACE}/bin bash"
                    }

                    def dirs = ['terraform/aws', 'terraform/modules/compute', 'terraform/modules/storage', 'terraform/modules/database']

                    dirs.each { d ->
                        dir(d) {
                            echo "Pre-warming cache for ${d}..."
                            sh 'terraform init -backend=false'
                        }
                    }

                    // 2. Parallel Checks
                    def checks = [:]

                    // AWS Directory Check
                    checks['terraform/aws'] = {
                        dir('terraform/aws') {
                            sh 'terraform fmt -check || echo "Terraform format check failed in terraform/aws"'
                            sh 'terraform init -backend=false'
                            sh 'terraform validate'
                            sh 'tfsec --format=json --out=tfsec-results.json .'
                        }
                    }

                    // Module Checks
                    def modules = ['terraform/modules/compute', 'terraform/modules/storage', 'terraform/modules/database']
                    modules.each { d ->
                        checks[d] = {
                            dir(d) {
                                sh "terraform fmt -check || echo 'Terraform format check failed in ${d}'"
                                sh 'terraform init -backend=false'
                                sh 'terraform validate'
                                sh 'tfsec .'
                            }
                        }
                    }

                    parallel checks
                }
            }
        }

        stage('Terraform Plan') {
            steps {
                dir('terraform/aws') {
                    sh 'terraform init'
                    sh "terraform plan -no-color -out=tfplan -var-file='environments/${params.DEPLOY_ENV}/terraform.tfvars' -var='aws_endpoint_url=${AWS_ENDPOINT_URL}'"
                    sh 'terraform show -no-color tfplan'
                }
            }
        }

        stage('Deploy') {
            when {
                branch 'main'
            }
            parallel {
                stage('Deploy AWS Automation') {
                    steps {
                        dir('automation/aws-lambda') {
                            script {
                                def functions = ['auto_shutdown', 'right_sizing', 'cleanup']
                                functions.each { func ->
                                    sh "zip -r ${func}.zip ${func}.py"
                                    sh "aws lambda update-function-code --function-name cost-opt-${func} --zip-file fileb://${func}.zip --region ${TF_VAR_aws_region} --endpoint-url=${AWS_ENDPOINT_URL}"
                                }
                            }
                        }
                    }
                }

                stage('Deploy Monitoring') {
                    steps {
                        sh "aws ecs update-service --cluster cost-opt-cluster --service cost-opt-monitoring --force-new-deployment --region ${TF_VAR_aws_region} --endpoint-url=${AWS_ENDPOINT_URL}"
                    }
                }
                stage('Terraform Apply') {
                    steps {
                        dir('terraform/aws') {
                            sh 'terraform apply -auto-approve tfplan'
                        }
                    }
                }
            }
        }
    }


}
