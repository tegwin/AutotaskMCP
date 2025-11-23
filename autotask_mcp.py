#!/usr/bin/env python3
"""
Autotask MCP Server - Enhanced Version

An MCP server that provides access to Autotask PSA platform for ticket management,
company and contact management, time entries, and more.

ENHANCED FEATURES:
- Accept names/emails instead of IDs for easier usage
- Automatic lookup of resources, companies, and contacts
- Backwards compatible with ID-based parameters
"""

import os
import json
import httpx
from typing import Optional, List, Dict, Any, Union
from enum import Enum
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict, field_validator
from mcp.server.fastmcp import FastMCP

# Initialize MCP server
mcp = FastMCP("autotask_mcp")

# Configuration
AUTOTASK_USERNAME = os.getenv("AUTOTASK_USERNAME", "")
AUTOTASK_SECRET = os.getenv("AUTOTASK_SECRET", "")
AUTOTASK_INTEGRATION_CODE = os.getenv("AUTOTASK_INTEGRATION_CODE", "")
AUTOTASK_API_URL = os.getenv("AUTOTASK_API_URL", "https://webservices.autotask.net/ATServicesRest/v1.0")

# Constants
API_TIMEOUT = 30.0
MAX_PAGE_SIZE = 500


class ResponseFormat(str, Enum):
    """Output format for tool responses."""
    MARKDOWN = "markdown"
    JSON = "json"


class TicketStatus(str, Enum):
    """Common Autotask ticket statuses."""
    NEW = "1"
    IN_PROGRESS = "5"
    COMPLETE = "5"
    WAITING_CUSTOMER = "8"
    WAITING_VENDOR = "13"


class TicketPriority(str, Enum):
    """Autotask ticket priority levels."""
    LOW = "1"
    MEDIUM = "2"
    HIGH = "3"
    CRITICAL = "4"


# Helper Functions

def _get_headers() -> Dict[str, str]:
    """Get authentication headers for Autotask API requests."""
    return {
        "ApiIntegrationcode": AUTOTASK_INTEGRATION_CODE,
        "UserName": AUTOTASK_USERNAME,
        "Secret": AUTOTASK_SECRET,
        "Content-Type": "application/json"
    }


def _validate_config() -> tuple[bool, str]:
    """Validate that required configuration is present."""
    if not AUTOTASK_USERNAME:
        return False, "AUTOTASK_USERNAME environment variable not set"
    if not AUTOTASK_SECRET:
        return False, "AUTOTASK_SECRET environment variable not set"
    if not AUTOTASK_INTEGRATION_CODE:
        return False, "AUTOTASK_INTEGRATION_CODE environment variable not set"
    return True, ""


def _handle_api_error(e: Exception) -> str:
    """Consistent error formatting across all tools."""
    if isinstance(e, httpx.HTTPStatusError):
        error_body = ""
        try:
            error_body = e.response.json()
            if isinstance(error_body, dict) and "errors" in error_body:
                errors = error_body["errors"]
                if errors and len(errors) > 0:
                    return f"Error: {errors[0].get('message', 'API request failed')}"
        except:
            pass
        
        if e.response.status_code == 400:
            return f"Error: Bad request. {error_body if error_body else 'Please check your input parameters.'}"
        elif e.response.status_code == 401:
            return "Error: Authentication failed. Please check your Autotask credentials."
        elif e.response.status_code == 403:
            return "Error: Permission denied. You don't have access to this resource."
        elif e.response.status_code == 404:
            return "Error: Resource not found. Please check the ID is correct."
        elif e.response.status_code == 429:
            return "Error: Rate limit exceeded. Please wait before making more requests."
        return f"Error: API request failed with status {e.response.status_code}"
    elif isinstance(e, httpx.TimeoutException):
        return "Error: Request timed out. Please try again."
    return f"Error: Unexpected error occurred: {str(e)}"


async def _make_api_request(
    method: str,
    endpoint: str,
    data: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Make an authenticated API request to Autotask."""
    is_valid, error_msg = _validate_config()
    if not is_valid:
        raise ValueError(error_msg)
    
    url = f"{AUTOTASK_API_URL}/{endpoint}"
    headers = _get_headers()
    
    async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
        if method.upper() == "GET":
            response = await client.get(url, headers=headers, params=params)
        elif method.upper() == "POST":
            response = await client.post(url, headers=headers, json=data)
        elif method.upper() == "PATCH":
            response = await client.patch(url, headers=headers, json=data)
        elif method.upper() == "DELETE":
            response = await client.delete(url, headers=headers)
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")
        
        response.raise_for_status()
        return response.json()


# ENHANCED LOOKUP FUNCTIONS

async def _lookup_company_id(company_name: str) -> Optional[int]:
    """Lookup a company ID by name."""
    try:
        query_body = {
            "MaxRecords": 5,
            "filter": [{"field": "companyName", "op": "contains", "value": company_name}]
        }
        
        result = await _make_api_request("POST", "Companies/query", data=query_body)
        companies = result.get("items", [])
        
        if not companies:
            return None
        
        # If exact match found, use it
        for company in companies:
            if company.get("companyName", "").lower() == company_name.lower():
                return company.get("id")
        
        # Otherwise use first result
        return companies[0].get("id")
    except:
        return None


async def _lookup_resource_id(resource_name: Optional[str] = None, resource_email: Optional[str] = None) -> Optional[int]:
    """Lookup a resource (user) ID by name or email."""
    try:
        filters = []
        
        if resource_email:
            filters.append({"field": "email", "op": "eq", "value": resource_email})
        elif resource_name:
            # Try to split name into first and last
            name_parts = resource_name.strip().split(None, 1)
            if len(name_parts) == 2:
                filters.append({"field": "firstName", "op": "contains", "value": name_parts[0]})
                filters.append({"field": "lastName", "op": "contains", "value": name_parts[1]})
            else:
                # Search in both first and last name
                filters.append({
                    "op": "or",
                    "items": [
                        {"field": "firstName", "op": "contains", "value": resource_name},
                        {"field": "lastName", "op": "contains", "value": resource_name}
                    ]
                })
        else:
            return None
        
        query_body = {
            "MaxRecords": 5,
            "filter": filters if len(filters) == 1 else [{"op": "and", "items": filters}]
        }
        
        result = await _make_api_request("POST", "Resources/query", data=query_body)
        resources = result.get("items", [])
        
        if not resources:
            return None
        
        # Return first match
        return resources[0].get("id")
    except:
        return None


async def _lookup_contact_id(
    contact_email: Optional[str] = None,
    contact_name: Optional[str] = None,
    company_id: Optional[int] = None
) -> Optional[int]:
    """Lookup a contact ID by email or name."""
    try:
        filters = []
        
        if contact_email:
            filters.append({"field": "emailAddress", "op": "eq", "value": contact_email})
        elif contact_name:
            name_parts = contact_name.strip().split(None, 1)
            if len(name_parts) == 2:
                filters.append({"field": "firstName", "op": "contains", "value": name_parts[0]})
                filters.append({"field": "lastName", "op": "contains", "value": name_parts[1]})
            else:
                filters.append({
                    "op": "or",
                    "items": [
                        {"field": "firstName", "op": "contains", "value": contact_name},
                        {"field": "lastName", "op": "contains", "value": contact_name}
                    ]
                })
        
        if company_id:
            filters.append({"field": "companyID", "op": "eq", "value": company_id})
        
        if not filters:
            return None
        
        query_body = {
            "MaxRecords": 5,
            "filter": filters if len(filters) == 1 else [{"op": "and", "items": filters}]
        }
        
        result = await _make_api_request("POST", "Contacts/query", data=query_body)
        contacts = result.get("items", [])
        
        if not contacts:
            return None
        
        return contacts[0].get("id")
    except:
        return None


def _format_ticket_markdown(ticket: Dict[str, Any]) -> str:
    """Format a ticket as markdown."""
    return f"""## Ticket #{ticket.get('ticketNumber', 'N/A')} - {ticket.get('title', 'No Title')}

**ID:** {ticket.get('id')}
**Status:** {ticket.get('status')} 
**Priority:** {ticket.get('priority')}
**Queue:** {ticket.get('queueID')}
**Assigned To:** {ticket.get('assignedResourceID', 'Unassigned')}
**Company:** {ticket.get('companyID')}
**Contact:** {ticket.get('contactID', 'None')}

**Created:** {ticket.get('createDate', 'N/A')}
**Last Modified:** {ticket.get('lastActivityDate', 'N/A')}

**Description:**
{ticket.get('description', 'No description')}

---"""


def _format_company_markdown(company: Dict[str, Any]) -> str:
    """Format a company as markdown."""
    return f"""## {company.get('companyName', 'Unknown Company')}

**ID:** {company.get('id')}
**Phone:** {company.get('phone', 'N/A')}
**Address:** {company.get('address1', 'N/A')}
**City:** {company.get('city', 'N/A')}
**State:** {company.get('state', 'N/A')}
**Zip:** {company.get('postalCode', 'N/A')}

---"""


def _format_contact_markdown(contact: Dict[str, Any]) -> str:
    """Format a contact as markdown."""
    return f"""## {contact.get('firstName', '')} {contact.get('lastName', '')}

**ID:** {contact.get('id')}
**Email:** {contact.get('emailAddress', 'N/A')}
**Phone:** {contact.get('phone', 'N/A')}
**Mobile:** {contact.get('mobilePhone', 'N/A')}
**Title:** {contact.get('title', 'N/A')}
**Company ID:** {contact.get('companyID')}

---"""


def _format_resource_markdown(resource: Dict[str, Any]) -> str:
    """Format a resource as markdown."""
    return f"""## {resource.get('firstName', '')} {resource.get('lastName', '')}

**ID:** {resource.get('id')}
**Email:** {resource.get('email', 'N/A')}
**Username:** {resource.get('userName', 'N/A')}
**Title:** {resource.get('title', 'N/A')}
**Active:** {resource.get('active', False)}

---"""


# Tools

class GetTicketInput(BaseModel):
    """Input model for retrieving a ticket by ID."""
    model_config = ConfigDict(str_strip_whitespace=True)
    
    ticket_id: int = Field(..., description="The Autotask ticket ID to retrieve", gt=0)
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' for human-readable or 'json' for machine-readable"
    )


@mcp.tool(
    name="autotask_get_ticket",
    annotations={
        "title": "Get Autotask Ticket",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def autotask_get_ticket(params: GetTicketInput) -> str:
    """Retrieve a single Autotask ticket by ID.
    
    This tool fetches detailed information about a specific ticket including its status,
    priority, description, assigned resources, and related company/contact information.
    
    Args:
        params (GetTicketInput): Contains:
            - ticket_id (int): The ticket ID to retrieve
            - response_format (ResponseFormat): Output format (markdown or json)
    
    Returns:
        str: Ticket information in the requested format
    """
    try:
        result = await _make_api_request("GET", f"Tickets/{params.ticket_id}")
        ticket = result.get("item", {})
        
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(ticket, indent=2)
        else:
            return _format_ticket_markdown(ticket)
            
    except Exception as e:
        return _handle_api_error(e)


class SearchTicketsInput(BaseModel):
    """Input model for searching tickets."""
    model_config = ConfigDict(str_strip_whitespace=True)
    
    company_id: Optional[int] = Field(None, description="Filter by company ID", gt=0)
    status: Optional[int] = Field(None, description="Filter by status ID")
    assigned_resource_id: Optional[int] = Field(None, description="Filter by assigned resource ID", gt=0)
    queue_id: Optional[int] = Field(None, description="Filter by queue ID", gt=0)
    limit: int = Field(default=20, description="Maximum number of tickets to return", ge=1, le=500)
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' for human-readable or 'json' for machine-readable"
    )


@mcp.tool(
    name="autotask_search_tickets",
    annotations={
        "title": "Search Autotask Tickets",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def autotask_search_tickets(params: SearchTicketsInput) -> str:
    """Search for Autotask tickets with optional filters.
    
    This tool allows you to search and filter tickets by company, status, assigned resource,
    queue, and more. Returns a list of matching tickets with key information.
    
    Args:
        params (SearchTicketsInput): Contains:
            - company_id (Optional[int]): Filter by company
            - status (Optional[int]): Filter by status ID
            - assigned_resource_id (Optional[int]): Filter by assigned resource
            - queue_id (Optional[int]): Filter by queue
            - limit (int): Maximum results (default 20, max 500)
            - response_format (ResponseFormat): Output format
    
    Returns:
        str: List of tickets in the requested format with pagination info
    """
    try:
        filters = []
        if params.company_id:
            filters.append({"field": "companyID", "op": "eq", "value": params.company_id})
        if params.status is not None:
            filters.append({"field": "status", "op": "eq", "value": params.status})
        if params.assigned_resource_id:
            filters.append({"field": "assignedResourceID", "op": "eq", "value": params.assigned_resource_id})
        if params.queue_id:
            filters.append({"field": "queueID", "op": "eq", "value": params.queue_id})
        
        query_body = {
            "MaxRecords": params.limit
        }
        
        if filters:
            if len(filters) == 1:
                query_body["filter"] = filters
            else:
                query_body["filter"] = [{"op": "and", "items": filters}]
        else:
            query_body["filter"] = [{"op": "exist", "field": "id"}]
        
        result = await _make_api_request("POST", "Tickets/query", data=query_body)
        
        tickets = result.get("items", [])
        
        if params.response_format == ResponseFormat.JSON:
            return json.dumps({
                "total": len(tickets),
                "tickets": tickets,
                "limit": params.limit
            }, indent=2)
        else:
            if not tickets:
                return "No tickets found matching the search criteria."
            
            output = f"# Found {len(tickets)} Ticket(s)\n\n"
            for ticket in tickets:
                output += _format_ticket_markdown(ticket)
            return output
            
    except Exception as e:
        return _handle_api_error(e)


class CreateTicketInput(BaseModel):
    """Input model for creating a new ticket - ENHANCED with name-based lookups."""
    model_config = ConfigDict(str_strip_whitespace=True)
    
    title: str = Field(..., description="Ticket title", min_length=1, max_length=255)
    description: str = Field(..., description="Ticket description", min_length=1)
    
    # Company - can use ID or name
    company_id: Optional[int] = Field(None, description="Company ID for the ticket", gt=0)
    company_name: Optional[str] = Field(None, description="Company name (alternative to company_id)")
    
    # Optional fields
    priority: int = Field(default=2, description="Priority: 1=Low, 2=Medium, 3=High, 4=Critical", ge=1, le=4)
    status: int = Field(default=1, description="Status ID (default 1=New)")
    queue_id: Optional[int] = Field(None, description="Queue ID", gt=0)
    due_date_time: Optional[str] = Field(None, description="Due date/time in ISO format (YYYY-MM-DDTHH:MM:SS)")
    
    # Contact - can use ID, email, or name
    contact_id: Optional[int] = Field(None, description="Contact ID", gt=0)
    contact_email: Optional[str] = Field(None, description="Contact email (alternative to contact_id)")
    contact_name: Optional[str] = Field(None, description="Contact name (alternative to contact_id)")
    
    # Assignment - can use ID or name
    assigned_resource_id: Optional[int] = Field(None, description="Assigned resource ID", gt=0)
    assigned_resource_name: Optional[str] = Field(None, description="Assigned resource name (alternative to assigned_resource_id)")
    assigned_resource_email: Optional[str] = Field(None, description="Assigned resource email (alternative to assigned_resource_id)")
    
    issue_type: Optional[int] = Field(None, description="Issue type ID")
    sub_issue_type: Optional[int] = Field(None, description="Sub-issue type ID")
    
    @field_validator('company_id', 'company_name')
    @classmethod
    def validate_company(cls, v, info):
        """Ensure at least one company identifier is provided."""
        if info.field_name == 'company_name' and v is None:
            # Check if company_id was provided
            if info.data.get('company_id') is None:
                raise ValueError("Either company_id or company_name must be provided")
        return v


@mcp.tool(
    name="autotask_create_ticket",
    annotations={
        "title": "Create Autotask Ticket",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True
    }
)
async def autotask_create_ticket(params: CreateTicketInput) -> str:
    """Create a new ticket in Autotask - ENHANCED with automatic name lookups.
    
    This tool creates a new ticket with the specified details. You can use either IDs
    or names for companies, contacts, and resources. The tool will automatically look up
    the IDs if names are provided.
    
    Args:
        params (CreateTicketInput): Contains:
            - title (str): Ticket title (required)
            - description (str): Ticket description (required)
            - company_id (int) OR company_name (str): Company identifier (required)
            - priority (int): Priority level (1-4, default 2)
            - status (int): Status ID (default 1)
            - contact_id/contact_email/contact_name (Optional): Contact identifier
            - assigned_resource_id/assigned_resource_name/assigned_resource_email (Optional): Assignment
            - queue_id, due_date_time, issue_type, sub_issue_type (Optional)
    
    Returns:
        str: JSON response with created ticket ID and details
    """
    try:
        # Resolve company ID
        company_id = params.company_id
        if not company_id and params.company_name:
            company_id = await _lookup_company_id(params.company_name)
            if not company_id:
                return f"Error: Could not find company '{params.company_name}'"
        
        if not company_id:
            return "Error: Either company_id or company_name must be provided"
        
        # Build ticket data
        ticket_data = {
            "companyID": company_id,
            "title": params.title,
            "description": params.description,
            "priority": params.priority,
            "status": params.status
        }
        
        # Resolve contact ID if provided
        if params.contact_id:
            ticket_data["contactID"] = params.contact_id
        elif params.contact_email or params.contact_name:
            contact_id = await _lookup_contact_id(
                contact_email=params.contact_email,
                contact_name=params.contact_name,
                company_id=company_id
            )
            if contact_id:
                ticket_data["contactID"] = contact_id
        
        # Resolve assigned resource ID if provided
        if params.assigned_resource_id:
            ticket_data["assignedResourceID"] = params.assigned_resource_id
        elif params.assigned_resource_name or params.assigned_resource_email:
            resource_id = await _lookup_resource_id(
                resource_name=params.assigned_resource_name,
                resource_email=params.assigned_resource_email
            )
            if resource_id:
                ticket_data["assignedResourceID"] = resource_id
        
        # Add optional fields
        if params.queue_id:
            ticket_data["queueID"] = params.queue_id
        if params.due_date_time:
            ticket_data["dueDateTime"] = params.due_date_time
        if params.issue_type:
            ticket_data["issueType"] = params.issue_type
        if params.sub_issue_type:
            ticket_data["subIssueType"] = params.sub_issue_type
        
        result = await _make_api_request("POST", "Tickets", data=ticket_data)
        
        if "itemId" in result:
            return f"✅ Ticket created successfully!\n\n**Ticket ID:** {result['itemId']}\n\n{json.dumps(result, indent=2)}"
        else:
            return json.dumps(result, indent=2)
            
    except Exception as e:
        return _handle_api_error(e)


class UpdateTicketInput(BaseModel):
    """Input model for updating a ticket."""
    model_config = ConfigDict(str_strip_whitespace=True)
    
    ticket_id: int = Field(..., description="Ticket ID to update", gt=0)
    title: Optional[str] = Field(None, description="New ticket title", max_length=255)
    description: Optional[str] = Field(None, description="New ticket description")
    status: Optional[int] = Field(None, description="New status ID")
    priority: Optional[int] = Field(None, description="New priority (1-4)", ge=1, le=4)
    assigned_resource_id: Optional[int] = Field(None, description="New assigned resource ID", gt=0)
    queue_id: Optional[int] = Field(None, description="New queue ID", gt=0)


@mcp.tool(
    name="autotask_update_ticket",
    annotations={
        "title": "Update Autotask Ticket",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def autotask_update_ticket(params: UpdateTicketInput) -> str:
    """Update an existing Autotask ticket.
    
    This tool allows you to update various fields on an existing ticket including title,
    description, status, priority, assignment, and queue.
    
    Args:
        params (UpdateTicketInput): Contains:
            - ticket_id (int): Ticket ID to update (required)
            - title (Optional[str]): New title
            - description (Optional[str]): New description
            - status (Optional[int]): New status ID
            - priority (Optional[int]): New priority (1-4)
            - assigned_resource_id (Optional[int]): New resource assignment
            - queue_id (Optional[int]): New queue assignment
    
    Returns:
        str: Success message with update confirmation
    """
    try:
        update_data = {"id": params.ticket_id}
        
        if params.title:
            update_data["title"] = params.title
        if params.description:
            update_data["description"] = params.description
        if params.status is not None:
            update_data["status"] = params.status
        if params.priority is not None:
            update_data["priority"] = params.priority
        if params.assigned_resource_id:
            update_data["assignedResourceID"] = params.assigned_resource_id
        if params.queue_id:
            update_data["queueID"] = params.queue_id
        
        if len(update_data) == 1:
            return "Error: No fields specified to update"
        
        result = await _make_api_request("PATCH", f"Tickets", data=update_data)
        
        if "itemId" in result:
            return f"✅ Ticket #{params.ticket_id} updated successfully!\n\n{json.dumps(result, indent=2)}"
        else:
            return json.dumps(result, indent=2)
            
    except Exception as e:
        return _handle_api_error(e)


class SearchCompaniesInput(BaseModel):
    """Input model for searching companies."""
    model_config = ConfigDict(str_strip_whitespace=True)
    
    company_name: Optional[str] = Field(None, description="Search by company name (partial match)")
    limit: int = Field(default=20, description="Maximum number of companies to return", ge=1, le=500)
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' for human-readable or 'json' for machine-readable"
    )


@mcp.tool(
    name="autotask_search_companies",
    annotations={
        "title": "Search Autotask Companies",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def autotask_search_companies(params: SearchCompaniesInput) -> str:
    """Search for Autotask companies.
    
    This tool allows you to search for companies by name or list all companies.
    Returns company details including contact information and address.
    
    Args:
        params (SearchCompaniesInput): Contains:
            - company_name (Optional[str]): Search by name (partial match)
            - limit (int): Maximum results (default 20, max 500)
            - response_format (ResponseFormat): Output format
    
    Returns:
        str: List of companies in the requested format
    """
    try:
        query_body = {
            "MaxRecords": params.limit
        }
        
        if params.company_name:
            query_body["filter"] = [{"field": "companyName", "op": "contains", "value": params.company_name}]
        else:
            query_body["filter"] = [{"op": "exist", "field": "id"}]
        
        result = await _make_api_request("POST", "Companies/query", data=query_body)
        
        companies = result.get("items", [])
        
        if params.response_format == ResponseFormat.JSON:
            return json.dumps({
                "total": len(companies),
                "companies": companies,
                "limit": params.limit
            }, indent=2)
        else:
            if not companies:
                return "No companies found matching the search criteria."
            
            output = f"# Found {len(companies)} Company(ies)\n\n"
            for company in companies:
                output += _format_company_markdown(company)
            return output
            
    except Exception as e:
        return _handle_api_error(e)


class GetCompanyInput(BaseModel):
    """Input model for retrieving a company by ID."""
    model_config = ConfigDict(str_strip_whitespace=True)
    
    company_id: int = Field(..., description="The Autotask company ID to retrieve", gt=0)
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' for human-readable or 'json' for machine-readable"
    )


@mcp.tool(
    name="autotask_get_company",
    annotations={
        "title": "Get Autotask Company",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def autotask_get_company(params: GetCompanyInput) -> str:
    """Retrieve a single Autotask company by ID.
    
    This tool fetches detailed information about a specific company including contact
    information, address, and other company details.
    
    Args:
        params (GetCompanyInput): Contains:
            - company_id (int): The company ID to retrieve
            - response_format (ResponseFormat): Output format (markdown or json)
    
    Returns:
        str: Company information in the requested format
    """
    try:
        result = await _make_api_request("GET", f"Companies/{params.company_id}")
        company = result.get("item", {})
        
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(company, indent=2)
        else:
            return _format_company_markdown(company)
            
    except Exception as e:
        return _handle_api_error(e)


class SearchContactsInput(BaseModel):
    """Input model for searching contacts."""
    model_config = ConfigDict(str_strip_whitespace=True)
    
    company_id: Optional[int] = Field(None, description="Filter by company ID", gt=0)
    email: Optional[str] = Field(None, description="Search by email address (partial match)")
    first_name: Optional[str] = Field(None, description="Search by first name (partial match)")
    last_name: Optional[str] = Field(None, description="Search by last name (partial match)")
    limit: int = Field(default=20, description="Maximum number of contacts to return", ge=1, le=500)
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' for human-readable or 'json' for machine-readable"
    )


@mcp.tool(
    name="autotask_search_contacts",
    annotations={
        "title": "Search Autotask Contacts",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def autotask_search_contacts(params: SearchContactsInput) -> str:
    """Search for Autotask contacts.
    
    This tool allows you to search for contacts by company, email, name, or list all contacts.
    Returns contact details including email, phone, and company association.
    
    Args:
        params (SearchContactsInput): Contains:
            - company_id (Optional[int]): Filter by company
            - email (Optional[str]): Search by email (partial match)
            - first_name (Optional[str]): Search by first name (partial match)
            - last_name (Optional[str]): Search by last name (partial match)
            - limit (int): Maximum results (default 20, max 500)
            - response_format (ResponseFormat): Output format
    
    Returns:
        str: List of contacts in the requested format
    """
    try:
        filters = []
        if params.company_id:
            filters.append({"field": "companyID", "op": "eq", "value": params.company_id})
        if params.email:
            filters.append({"field": "emailAddress", "op": "contains", "value": params.email})
        if params.first_name:
            filters.append({"field": "firstName", "op": "contains", "value": params.first_name})
        if params.last_name:
            filters.append({"field": "lastName", "op": "contains", "value": params.last_name})
        
        query_body = {
            "MaxRecords": params.limit
        }
        
        if filters:
            if len(filters) == 1:
                query_body["filter"] = filters
            else:
                query_body["filter"] = [{"op": "and", "items": filters}]
        else:
            query_body["filter"] = [{"op": "exist", "field": "id"}]
        
        result = await _make_api_request("POST", "Contacts/query", data=query_body)
        
        contacts = result.get("items", [])
        
        if params.response_format == ResponseFormat.JSON:
            return json.dumps({
                "total": len(contacts),
                "contacts": contacts,
                "limit": params.limit
            }, indent=2)
        else:
            if not contacts:
                return "No contacts found matching the search criteria."
            
            output = f"# Found {len(contacts)} Contact(s)\n\n"
            for contact in contacts:
                output += _format_contact_markdown(contact)
            return output
            
    except Exception as e:
        return _handle_api_error(e)


class SearchResourcesInput(BaseModel):
    """Input model for searching resources (users)."""
    model_config = ConfigDict(str_strip_whitespace=True)
    
    email: Optional[str] = Field(None, description="Search by email address (exact match)")
    first_name: Optional[str] = Field(None, description="Search by first name (partial match)")
    last_name: Optional[str] = Field(None, description="Search by last name (partial match)")
    user_name: Optional[str] = Field(None, description="Search by username (partial match)")
    active_only: bool = Field(default=True, description="Only return active resources")
    limit: int = Field(default=20, description="Maximum number of resources to return", ge=1, le=500)
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' for human-readable or 'json' for machine-readable"
    )


@mcp.tool(
    name="autotask_search_resources",
    annotations={
        "title": "Search Autotask Resources (Users)",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def autotask_search_resources(params: SearchResourcesInput) -> str:
    """Search for Autotask resources (users/employees).
    
    This tool allows you to search for resources by email, name, or username.
    Returns resource details including email, title, and active status.
    
    Args:
        params (SearchResourcesInput): Contains:
            - email (Optional[str]): Search by email (exact match)
            - first_name (Optional[str]): Search by first name (partial match)
            - last_name (Optional[str]): Search by last name (partial match)
            - user_name (Optional[str]): Search by username (partial match)
            - active_only (bool): Only return active resources (default True)
            - limit (int): Maximum results (default 20, max 500)
            - response_format (ResponseFormat): Output format
    
    Returns:
        str: List of resources in the requested format
    """
    try:
        filters = []
        
        if params.email:
            filters.append({"field": "email", "op": "eq", "value": params.email})
        if params.first_name:
            filters.append({"field": "firstName", "op": "contains", "value": params.first_name})
        if params.last_name:
            filters.append({"field": "lastName", "op": "contains", "value": params.last_name})
        if params.user_name:
            filters.append({"field": "userName", "op": "contains", "value": params.user_name})
        if params.active_only:
            filters.append({"field": "active", "op": "eq", "value": True})
        
        query_body = {
            "MaxRecords": params.limit
        }
        
        if filters:
            if len(filters) == 1:
                query_body["filter"] = filters
            else:
                query_body["filter"] = [{"op": "and", "items": filters}]
        else:
            query_body["filter"] = [{"op": "exist", "field": "id"}]
        
        result = await _make_api_request("POST", "Resources/query", data=query_body)
        
        resources = result.get("items", [])
        
        if params.response_format == ResponseFormat.JSON:
            return json.dumps({
                "total": len(resources),
                "resources": resources,
                "limit": params.limit
            }, indent=2)
        else:
            if not resources:
                return "No resources found matching the search criteria."
            
            output = f"# Found {len(resources)} Resource(s)\n\n"
            for resource in resources:
                output += _format_resource_markdown(resource)
            return output
            
    except Exception as e:
        return _handle_api_error(e)


class AddTicketNoteInput(BaseModel):
    """Input model for adding a note to a ticket."""
    model_config = ConfigDict(str_strip_whitespace=True)
    
    ticket_id: int = Field(..., description="Ticket ID to add note to", gt=0)
    title: str = Field(..., description="Note title", min_length=1, max_length=255)
    description: str = Field(..., description="Note content/description", min_length=1)
    note_type: int = Field(default=1, description="Note type: 1=General, 2=Time Entry, etc.")
    publish: int = Field(default=1, description="Publish level: 1=All Autotask Users, 2=Internal Only, 3=Internal & Co-managed")


@mcp.tool(
    name="autotask_add_ticket_note",
    annotations={
        "title": "Add Note to Autotask Ticket",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True
    }
)
async def autotask_add_ticket_note(params: AddTicketNoteInput) -> str:
    """Add a note to an existing Autotask ticket.
    
    This tool creates a new note on a ticket. Notes can be used to document progress,
    communications, or any other relevant information about the ticket.
    
    Args:
        params (AddTicketNoteInput): Contains:
            - ticket_id (int): Ticket to add note to (required)
            - title (str): Note title (required)
            - description (str): Note content (required)
            - note_type (int): Type of note (default 1)
            - publish (int): Who can see the note (default 1)
    
    Returns:
        str: Success message with created note details
    """
    try:
        note_data = {
            "ticketID": params.ticket_id,
            "title": params.title,
            "description": params.description,
            "noteType": params.note_type,
            "publish": params.publish
        }
        
        result = await _make_api_request("POST", "TicketNotes", data=note_data)
        
        if "itemId" in result:
            return f"✅ Note added to ticket #{params.ticket_id} successfully!\n\n**Note ID:** {result['itemId']}\n\n" + json.dumps(result, indent=2)
        else:
            return json.dumps(result, indent=2)
            
    except Exception as e:
        return _handle_api_error(e)


class CreateTimeEntryInput(BaseModel):
    """Input model for creating a time entry - ENHANCED with name-based lookups."""
    model_config = ConfigDict(str_strip_whitespace=True)
    
    ticket_id: int = Field(..., description="Ticket ID to log time against", gt=0)
    
    # Resource - can use ID, name, or email
    resource_id: Optional[int] = Field(None, description="Resource ID (user) who worked on the ticket", gt=0)
    resource_name: Optional[str] = Field(None, description="Resource name (alternative to resource_id)")
    resource_email: Optional[str] = Field(None, description="Resource email (alternative to resource_id)")
    
    hours_worked: float = Field(..., description="Hours worked (e.g., 1.5 for 1 hour 30 minutes)", gt=0)
    date_worked: Optional[str] = Field(None, description="Date worked in YYYY-MM-DD format (defaults to today)")
    summary_notes: Optional[str] = Field(None, description="Summary/description of work performed")
    internal_notes: Optional[str] = Field(None, description="Internal notes (not visible to customer)")
    hours_to_bill: Optional[float] = Field(None, description="Billable hours (defaults to hours_worked if not specified)", gt=0)
    time_entry_type: int = Field(default=1, description="Time entry type: 1=Regular, 2=Travel, 3=Wait, etc. (default 1)")
    offset_hours: float = Field(default=0.0, description="Timezone offset in hours (default 0.0 for UTC)")


@mcp.tool(
    name="autotask_create_time_entry",
    annotations={
        "title": "Create Autotask Time Entry",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True
    }
)
async def autotask_create_time_entry(params: CreateTimeEntryInput) -> str:
    """Create a time entry for an Autotask ticket - ENHANCED with automatic name lookups.
    
    This tool logs time worked against a ticket. You can specify the resource (user) by
    ID, name, or email - the tool will automatically look up the ID if needed.
    
    Args:
        params (CreateTimeEntryInput): Contains:
            - ticket_id (int): Ticket to log time against (required)
            - resource_id (int) OR resource_name/resource_email (str): User identifier (required)
            - hours_worked (float): Hours worked (required)
            - date_worked (Optional[str]): Date in YYYY-MM-DD format (defaults to today)
            - summary_notes (Optional[str]): Work description
            - internal_notes (Optional[str]): Internal notes
            - hours_to_bill (Optional[float]): Billable hours (defaults to hours_worked)
            - time_entry_type (int): Entry type (default 1=Regular)
            - offset_hours (float): Timezone offset (default 0.0)
    
    Returns:
        str: Success message with created time entry details
    """
    try:
        # Resolve resource ID
        resource_id = params.resource_id
        if not resource_id and (params.resource_name or params.resource_email):
            resource_id = await _lookup_resource_id(
                resource_name=params.resource_name,
                resource_email=params.resource_email
            )
            if not resource_id:
                search_term = params.resource_email or params.resource_name
                return f"Error: Could not find resource '{search_term}'"
        
        if not resource_id:
            return "Error: Either resource_id, resource_name, or resource_email must be provided"
        
        # Use today's date if not specified
        date_worked = params.date_worked
        if not date_worked:
            from datetime import date
            date_worked = date.today().strftime("%Y-%m-%d")
        
        # Build time entry data
        time_entry_data = {
            "ticketID": params.ticket_id,
            "resourceID": resource_id,
            "dateWorked": date_worked,
            "hoursWorked": params.hours_worked,
            "timeEntryType": params.time_entry_type,
            "offsetHours": params.offset_hours
        }
        
        # Add optional fields if provided
        if params.summary_notes:
            time_entry_data["summaryNotes"] = params.summary_notes
        
        if params.internal_notes:
            time_entry_data["internalNotes"] = params.internal_notes
        
        if params.hours_to_bill is not None:
            time_entry_data["hoursToBill"] = params.hours_to_bill
        else:
            time_entry_data["hoursToBill"] = params.hours_worked
        
        result = await _make_api_request("POST", "TimeEntries", data=time_entry_data)
        
        if "itemId" in result:
            return f"""✅ Time entry created successfully!

**Time Entry ID:** {result['itemId']}
**Ticket ID:** {params.ticket_id}
**Hours Worked:** {params.hours_worked}
**Hours to Bill:** {time_entry_data['hoursToBill']}
**Date:** {date_worked}
**Resource ID:** {resource_id}

{json.dumps(result, indent=2)}"""
        else:
            return json.dumps(result, indent=2)
            
    except Exception as e:
        return _handle_api_error(e)


# Run the server
if __name__ == "__main__":
    mcp.run()