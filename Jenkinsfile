pipeline {
    agent any 
    
    environment {
        // This assumes you've added your Neon password to Jenkins Credentials
        NEON_PASSWORD = credentials('NEON_DB_PASSWORD') 
    }

    stages {
        stage('Checkout') {
            steps {
                // Jenkins pulls your latest code
                checkout scm
            }
        }

        stage('Build Container') {
            steps {
                // Build the Docker image we already created
                sh 'docker build -t nifty-oracle-scraper .'
            }
        }

        stage('Execute ETL') {
            steps {
                // Run the container and pass the Neon password securely
                sh 'docker run --rm -e NEON_PASSWORD=${NEON_PASSWORD} nifty-oracle-scraper'
            }
        }
    }
    
    post {
        success {
            echo 'Pipeline completed successfully. Data pushed to Neon DB.'
        }
        failure {
            echo 'Pipeline failed. Check the logs for stock-specific errors.'
        }
    }
}
