#!/bin/bash

# Set environment variables for development
export DEBUG=1
export FIREBASE_CRED_PATH=firebase-cred.json
export SECRET_KEY="django-insecure-ksgg^#ftx9*t8rh0e*y+j=g1m&&i8(-3nh*tm"
export EMAIL_HOST=localhost
export EMAIL_HOST_USER=test@example.com
export EMAIL_HOST_PASSWORD=password
export STRIPE_TEST_API_KEY=sk_test_placeholder
export STRIPE_PUB_TEST_KEY=pk_test_placeholder
export STRIPE_WEBHOOK_TEST_API_KEY=whsec_placeholder
export GOOGLE_ANALYTICS=GA-placeholder

# Run the command passed as arguments
"$@" 