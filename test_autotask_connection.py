#!/usr/bin/env python3
"""
Test script for Autotask MCP Server
Use this to verify your API credentials work before configuring Claude Desktop
"""

import os
import sys
import json
import httpx
from typing import Dict, Any

def get_credentials() -> Dict[str, str]:
    """Get credentials from environment or prompt user."""
    creds = {}
    
    print("=" * 60)
    print("Autotask MCP Server - Connection Test")
    print("=" * 60)
    print()
    
    # Try to get from environment first
    creds['username'] = os.getenv('AUTOTASK_USERNAME', '')
    creds['secret'] = os.getenv('AUTOTASK_SECRET', '')
    creds['integration_code'] = os.getenv('AUTOTASK_INTEGRATION_CODE', '')
    creds['api_url'] = os.getenv('AUTOTASK_API_URL', '')
    
    # Prompt for missing values
    if not creds['username']:
        creds['username'] = input("Autotask Username: ").strip()
    
    if not creds['secret']:
        creds['secret'] = input("Autotask Secret: ").strip()
    
    if not creds['integration_code']:
        creds['integration_code'] = input("Autotask Integration Code: ").strip()
    
    if not creds['api_url']:
        print("\nCommon API URLs:")
        print("  1. https://webservices2.autotask.net/ATServicesRest/v1.0")
        print("  2. https://webservices4.autotask.net/ATServicesRest/v1.0")
        print("  3. https://webservices5.autotask.net/ATServicesRest/v1.0")
        print("  4. https://webservices11.autotask.net/ATServicesRest/v1.0")
        creds['api_url'] = input("\nAutotask API URL: ").strip()
    
    return creds

def test_connection(creds: Dict[str, str]) -> bool:
    """Test the Autotask API connection."""
    print("\n" + "=" * 60)
    print("Testing Connection...")
    print("=" * 60)
    
    headers = {
        "ApiIntegrationcode": creds['integration_code'],
        "UserName": creds['username'],
        "Secret": creds['secret'],
        "Content-Type": "application/json"
    }
    
    # Test 1: Get account info
    print("\n[Test 1] Getting account information...")
    try:
        with httpx.Client(timeout=30.0) as client:
            # Autotask query endpoints use POST, not GET
            # Autotask requires a filter field even for basic queries
            query_body = {
                "MaxRecords": 1,
                "filter": [
                    {"op": "exist", "field": "id"}
                ]
            }
            response = client.post(
                f"{creds['api_url']}/Companies/query",
                headers=headers,
                json=query_body
            )
            
            if response.status_code == 200:
                print("✅ Authentication successful!")
                data = response.json()
                if 'items' in data and len(data['items']) > 0:
                    company = data['items'][0]
                    print(f"✅ Retrieved sample company: {company.get('companyName', 'N/A')}")
                return True
            elif response.status_code == 401:
                print("❌ Authentication failed - Check your username and secret")
                print(f"   Response: {response.text}")
                return False
            elif response.status_code == 403:
                print("❌ Permission denied - Check API user permissions")
                print(f"   Response: {response.text}")
                return False
            else:
                print(f"❌ API request failed with status {response.status_code}")
                print(f"   Response: {response.text}")
                return False
                
    except httpx.ConnectError as e:
        print(f"❌ Connection error - Check your API URL")
        print(f"   Error: {str(e)}")
        return False
    except httpx.TimeoutException:
        print("❌ Request timed out - Check your network connection")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {str(e)}")
        return False

def test_ticket_access(creds: Dict[str, str]) -> bool:
    """Test ticket read access."""
    print("\n[Test 2] Testing ticket access...")
    
    headers = {
        "ApiIntegrationcode": creds['integration_code'],
        "UserName": creds['username'],
        "Secret": creds['secret'],
        "Content-Type": "application/json"
    }
    
    try:
        with httpx.Client(timeout=30.0) as client:
            # Autotask query endpoints use POST
            # Autotask requires a filter field even for basic queries
            query_body = {
                "MaxRecords": 1,
                "filter": [
                    {"op": "exist", "field": "id"}
                ]
            }
            response = client.post(
                f"{creds['api_url']}/Tickets/query",
                headers=headers,
                json=query_body
            )
            
            if response.status_code == 200:
                data = response.json()
                if 'items' in data and len(data['items']) > 0:
                    ticket = data['items'][0]
                    print(f"✅ Ticket access successful!")
                    print(f"   Sample ticket: #{ticket.get('ticketNumber', 'N/A')} - {ticket.get('title', 'N/A')}")
                else:
                    print("⚠️  Ticket access works but no tickets found")
                return True
            else:
                print(f"⚠️  Could not access tickets (status {response.status_code})")
                return False
                
    except Exception as e:
        print(f"⚠️  Error accessing tickets: {str(e)}")
        return False

def generate_config(creds: Dict[str, str]):
    """Generate Claude Desktop configuration."""
    print("\n" + "=" * 60)
    print("Configuration for Claude Desktop")
    print("=" * 60)
    
    # Get the current directory
    current_dir = os.path.abspath(os.path.dirname(__file__))
    mcp_file = os.path.join(current_dir, "autotask_mcp.py")
    
    config = {
        "mcpServers": {
            "autotask": {
                "command": "python",
                "args": [mcp_file],
                "env": {
                    "AUTOTASK_USERNAME": creds['username'],
                    "AUTOTASK_SECRET": creds['secret'],
                    "AUTOTASK_INTEGRATION_CODE": creds['integration_code'],
                    "AUTOTASK_API_URL": creds['api_url']
                }
            }
        }
    }
    
    print("\nAdd this to your Claude Desktop config file:")
    print("\nmacOS: ~/Library/Application Support/Claude/claude_desktop_config.json")
    print("Windows: %APPDATA%\\Claude\\claude_desktop_config.json")
    print("\n" + "-" * 60)
    print(json.dumps(config, indent=2))
    print("-" * 60)
    
    # Offer to save to file
    save = input("\nSave this configuration to a file? (y/n): ").strip().lower()
    if save == 'y':
        output_file = "claude_config_generated.json"
        with open(output_file, 'w') as f:
            json.dump(config, f, indent=2)
        print(f"✅ Configuration saved to: {output_file}")

def main():
    """Main test function."""
    try:
        # Get credentials
        creds = get_credentials()
        
        # Validate required fields
        if not all([creds['username'], creds['secret'], creds['integration_code'], creds['api_url']]):
            print("\n❌ Error: All credentials are required")
            sys.exit(1)
        
        # Test connection
        connection_ok = test_connection(creds)
        
        if connection_ok:
            # Test ticket access
            test_ticket_access(creds)
            
            # Generate configuration
            generate_config(creds)
            
            print("\n" + "=" * 60)
            print("✅ All tests completed!")
            print("=" * 60)
            print("\nNext steps:")
            print("1. Copy the configuration to your Claude Desktop config file")
            print("2. Restart Claude Desktop")
            print("3. Start chatting with Claude about your Autotask data!")
            print()
        else:
            print("\n" + "=" * 60)
            print("❌ Connection test failed")
            print("=" * 60)
            print("\nPlease check your credentials and try again.")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n\nTest cancelled by user.")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Unexpected error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
