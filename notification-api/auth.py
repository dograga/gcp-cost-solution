"""Authentication module for GCP OAuth"""

import logging
from typing import Optional
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from google.oauth2 import id_token
from google.auth.transport import requests
import config

logger = logging.getLogger(__name__)

# Security scheme
security = HTTPBearer()


def verify_token(credentials: HTTPAuthorizationCredentials = Security(security)) -> dict:
    """
    Verify Google OAuth token and return user info.
    
    Returns:
        dict: User information including email
        
    Raises:
        HTTPException: If token is invalid
    """
    token = credentials.credentials
    
    try:
        # Verify the token
        idinfo = id_token.verify_oauth2_token(
            token, 
            requests.Request(),
            config.GCP_OAUTH_CLIENT_ID
        )
        
        # Verify the issuer
        if idinfo['iss'] not in ['accounts.google.com', 'https://accounts.google.com']:
            raise ValueError('Wrong issuer.')
        
        # Extract user information
        user_info = {
            'email': idinfo.get('email'),
            'name': idinfo.get('name'),
            'user_id': idinfo.get('sub'),
            'email_verified': idinfo.get('email_verified', False)
        }
        
        logger.info(f"Authenticated user: {user_info['email']}")
        return user_info
        
    except ValueError as e:
        logger.error(f"Token verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        logger.error(f"Authentication error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_current_user(credentials: HTTPAuthorizationCredentials = Security(security)) -> str:
    """
    Get current authenticated user's email.
    
    Returns:
        str: User's email address
    """
    user_info = verify_token(credentials)
    return user_info['email']


def get_current_user_info(credentials: HTTPAuthorizationCredentials = Security(security)) -> dict:
    """
    Get current authenticated user's full information.
    
    Returns:
        dict: User information
    """
    return verify_token(credentials)
