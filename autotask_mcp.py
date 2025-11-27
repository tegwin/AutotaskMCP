#!/usr/bin/env python3
"""
Autotask MCP Server v3

An MCP server that provides access to Autotask PSA platform for ticket management,
company and contact management, time entries, ticket notes, and more.

Key Features:
- Ticket CRUD operations
- TicketNotes creation (proper endpoint: /Tickets/{id}/Notes)
- TimeEntries creation (proper endpoint: /TimeEntries)
- Company and Contact search
- Resource lookup

Authentication: Uses username, secret, and API integration code in headers.
"""

import os
import json
import httpx
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from mcp.server.fastmcp import FastMCP

# Initialize MCP server
mcp = FastMCP("autotask")

# =============================================================================
# CONFIGURATION
# =============================================================================

AUTOTASK_USERNAME = os.getenv("AUTOTASK_USERNAME", "")
AUTOTASK_SECRET = os.getenv("AUTOTASK_SECRET", "")
AUTOTASK_INTEGRATION_CODE = os.getenv("AUTOTASK_INTEGRATION_CODE", "")
AUTOTASK_API_URL = os.getenv("AUTOTASK_API_URL", "https://webservices16.autotask.net/ATServicesRest/v1.0")

API_TIMEOUT = 30.0
MAX_PAGE_SIZE = 500

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _get_headers() -> Dict[str, str]:
    """Get authentication headers for Autotask API requests."""
    return {
        "Content-Type": "application/json",
        "UserName": AUTOTASK_USERNAME,
        "Secret": AUTOTASK_SECRET,
        "ApiIntegrationCode": AUTOTASK_INTEGRATION_CODE,
    }


def _make_request(
    method: str,
    endpoint: str,
    data: Optional[Dict] = None,
    params: Optional[Dict] = None
) -> Dict[str, Any]:
    """Make an HTTP request to the Autotask API."""
    url = f"{AUTOTASK_API_URL}/{endpoint}"
    headers = _get_headers()
    
    try:
        with httpx.Client(timeout=API_TIMEOUT) as client:
            if method.upper() == "GET":
                response = client.get(url, headers=headers, params=params)
            elif method.upper() == "POST":
                response = client.post(url, headers=headers, json=data)
            elif method.upper() == "PATCH":
                response = client.patch(url, headers=headers, json=data)
            elif method.upper() == "PUT":
                response = client.put(url, headers=headers, json=data)
            elif method.upper() == "DELETE":
                response = client.delete(url, headers=headers)
            else:
                return {"error": f"Unsupported HTTP method: {method}"}
            
            # Log response for debugging
            if response.status_code >= 400:
                return {
                    "error": f"API returned status {response.status_code}",
                    "status_code": response.status_code,
                    "response_text": response.text,
                    "url": url,
                    "method": method
                }
            
            if response.text:
                return response.json()
            return {"success": True}
            
    except httpx.TimeoutException:
        return {"error": "Request timed out"}
    except httpx.RequestError as e:
        return {"error": f"Request failed: {str(e)}"}
    except json.JSONDecodeError:
        return {"error": "Failed to parse API response", "raw_response": response.text}


def _query_entity(entity: str, filters: List[Dict], fields: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Query an Autotask entity using the query endpoint.
    
    Args:
        entity: Entity name (e.g., "Tickets", "Companies", "Resources")
        filters: List of filter dictionaries with 'field', 'op', 'value'
        fields: Optional list of fields to return
    
    Returns:
        API response dictionary
    """
    query_body = {"filter": filters}
    if fields:
        query_body["includeFields"] = fields
    
    return _make_request("POST", f"{entity}/query", data=query_body)


def _format_datetime_for_api(dt: Optional[datetime] = None) -> str:
    """Format datetime for Autotask API (ISO 8601 UTC)."""
    if dt is None:
        dt = datetime.now(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _format_date_for_api(dt: Optional[datetime] = None) -> str:
    """Format date for Autotask API (YYYY-MM-DD)."""
    if dt is None:
        dt = datetime.now(timezone.utc)
    return dt.strftime("%Y-%m-%d")


# =============================================================================
# INPUT MODELS
# =============================================================================

class GetTicketInput(BaseModel):
    """Input for getting a ticket by ID."""
    ticket_id: int = Field(..., description="The ticket ID to retrieve")


class SearchTicketsInput(BaseModel):
    """Input for searching tickets."""
    company_id: Optional[int] = Field(None, description="Filter by company ID")
    status: Optional[int] = Field(None, description="Filter by status ID")
    priority: Optional[int] = Field(None, description="Filter by priority ID")
    assigned_resource_id: Optional[int] = Field(None, description="Filter by assigned resource ID")
    queue_id: Optional[int] = Field(None, description="Filter by queue ID")
    title_contains: Optional[str] = Field(None, description="Filter by title containing this text")
    max_results: Optional[int] = Field(50, description="Maximum number of results to return")


class CreateTicketInput(BaseModel):
    """Input for creating a ticket."""
    title: str = Field(..., description="Ticket title/subject")
    description: Optional[str] = Field(None, description="Ticket description")
    company_id: int = Field(..., description="Company ID for the ticket")
    status: Optional[int] = Field(1, description="Status ID (default: 1 = New)")
    priority: Optional[int] = Field(2, description="Priority ID (default: 2 = Medium)")
    queue_id: Optional[int] = Field(None, description="Queue ID to assign the ticket to")
    assigned_resource_id: Optional[int] = Field(None, description="Resource ID to assign the ticket to")
    assigned_resource_role_id: Optional[int] = Field(None, description="Role ID for the assigned resource")
    due_date_time: Optional[str] = Field(None, description="Due date/time in ISO format")
    ticket_type: Optional[int] = Field(1, description="Ticket type (1=Service Request, 2=Incident, etc.)")


class UpdateTicketInput(BaseModel):
    """Input for updating a ticket."""
    ticket_id: int = Field(..., description="The ticket ID to update")
    title: Optional[str] = Field(None, description="New ticket title")
    description: Optional[str] = Field(None, description="New ticket description")
    status: Optional[int] = Field(None, description="New status ID")
    priority: Optional[int] = Field(None, description="New priority ID")
    queue_id: Optional[int] = Field(None, description="New queue ID")
    assigned_resource_id: Optional[int] = Field(None, description="New assigned resource ID")
    assigned_resource_role_id: Optional[int] = Field(None, description="New role ID for assigned resource")
    due_date_time: Optional[str] = Field(None, description="New due date/time in ISO format")


class CreateTicketNoteInput(BaseModel):
    """
    Input for creating a ticket note.
    
    Required by Autotask API:
    - ticketId: The ticket to add the note to
    - description: The note content
    - noteType: Type of note (picklist - get values from your Autotask instance)
    - publish: Visibility setting (1=All Autotask Users, 2=Internal Only, etc.)
    """
    ticket_id: int = Field(..., description="The ticket ID to add the note to")
    title: Optional[str] = Field("", description="Note title (may be required depending on ticket category settings)")
    description: str = Field(..., description="The note content/body")
    note_type: int = Field(1, description="Note type ID (1=Task Detail, 2=Resolution, 3=Summary, etc. - varies by instance)")
    publish: int = Field(1, description="Publish/visibility (1=All Autotask Users, 2=Internal Only, 3=Datto Internal)")


class CreateTimeEntryInput(BaseModel):
    """
    Input for creating a time entry.
    
    Required by Autotask API:
    - ticketId OR taskId: What the time is logged against
    - resourceId: The resource who did the work
    - roleId: The role for the resource (must be valid for the resource)
    - dateWorked: The date the work was performed
    - hoursWorked: Hours worked (> 0 and <= 24)
    - summaryNotes: Required for ticket time entries
    
    Optional but commonly used:
    - billingCodeId: Work type (General) allocation code
    - contractId: Contract to bill against
    - startDateTime/endDateTime: Start and end times
    - internalNotes: Internal notes (not visible to customers)
    - hoursToBill: Billable hours (if different from hoursWorked)
    - isNonBillable: Whether the time is non-billable
    - showOnInvoice: Whether to show on invoice
    """
    ticket_id: Optional[int] = Field(None, description="Ticket ID to log time against (required if no task_id)")
    task_id: Optional[int] = Field(None, description="Task ID to log time against (required if no ticket_id)")
    resource_id: int = Field(..., description="Resource ID who performed the work")
    role_id: int = Field(..., description="Role ID for the resource (must be valid for the resource)")
    date_worked: Optional[str] = Field(None, description="Date worked in YYYY-MM-DD format (defaults to today)")
    hours_worked: float = Field(..., description="Hours worked (must be > 0 and <= 24)")
    summary_notes: str = Field(..., description="Summary/description of work performed (required for ticket time entries)")
    internal_notes: Optional[str] = Field(None, description="Internal notes (not visible to customers)")
    billing_code_id: Optional[int] = Field(None, description="Work Type/Billing Code ID")
    contract_id: Optional[int] = Field(None, description="Contract ID to bill against")
    hours_to_bill: Optional[float] = Field(None, description="Billable hours (defaults to hours_worked)")
    is_non_billable: Optional[bool] = Field(None, description="Whether the time is non-billable")
    show_on_invoice: Optional[bool] = Field(None, description="Whether to show on invoice")
    start_date_time: Optional[str] = Field(None, description="Start time in ISO format")
    end_date_time: Optional[str] = Field(None, description="End time in ISO format")


class SearchCompaniesInput(BaseModel):
    """Input for searching companies."""
    name_contains: Optional[str] = Field(None, description="Filter by company name containing this text")
    is_active: Optional[bool] = Field(True, description="Filter by active status")
    max_results: Optional[int] = Field(50, description="Maximum number of results")


class GetCompanyInput(BaseModel):
    """Input for getting a company by ID."""
    company_id: int = Field(..., description="The company ID to retrieve")


class SearchContactsInput(BaseModel):
    """Input for searching contacts."""
    company_id: Optional[int] = Field(None, description="Filter by company ID")
    email_contains: Optional[str] = Field(None, description="Filter by email containing this text")
    first_name: Optional[str] = Field(None, description="Filter by first name")
    last_name: Optional[str] = Field(None, description="Filter by last name")
    max_results: Optional[int] = Field(50, description="Maximum number of results")


class SearchResourcesInput(BaseModel):
    """Input for searching resources (users/technicians)."""
    first_name: Optional[str] = Field(None, description="Filter by first name")
    last_name: Optional[str] = Field(None, description="Filter by last name")
    email: Optional[str] = Field(None, description="Filter by email")
    is_active: Optional[bool] = Field(True, description="Filter by active status")
    max_results: Optional[int] = Field(50, description="Maximum number of results")


class GetResourceInput(BaseModel):
    """Input for getting a resource by ID."""
    resource_id: int = Field(..., description="The resource ID to retrieve")


class GetPicklistValuesInput(BaseModel):
    """Input for getting picklist values for a field."""
    entity: str = Field(..., description="Entity name (e.g., 'Tickets', 'TicketNotes', 'TimeEntries')")
    field: str = Field(..., description="Field name (e.g., 'status', 'priority', 'noteType', 'publish')")


# =============================================================================
# TOOLS - TICKETS
# =============================================================================

@mcp.tool()
async def autotask_get_ticket(params: GetTicketInput) -> str:
    """Get a ticket by ID from Autotask."""
    result = _make_request("GET", f"Tickets/{params.ticket_id}")
    
    if "error" in result:
        return f"Error: {result['error']}\nDetails: {result.get('response_text', 'No details')}"
    
    ticket = result.get("item", result)
    return json.dumps(ticket, indent=2)


@mcp.tool()
async def autotask_search_tickets(params: SearchTicketsInput) -> str:
    """Search for tickets in Autotask with various filters."""
    filters = []
    
    if params.company_id:
        filters.append({"field": "companyID", "op": "eq", "value": params.company_id})
    if params.status:
        filters.append({"field": "status", "op": "eq", "value": params.status})
    if params.priority:
        filters.append({"field": "priority", "op": "eq", "value": params.priority})
    if params.assigned_resource_id:
        filters.append({"field": "assignedResourceID", "op": "eq", "value": params.assigned_resource_id})
    if params.queue_id:
        filters.append({"field": "queueID", "op": "eq", "value": params.queue_id})
    if params.title_contains:
        filters.append({"field": "title", "op": "contains", "value": params.title_contains})
    
    if not filters:
        # Default: get recent tickets
        filters.append({"field": "id", "op": "gt", "value": 0})
    
    result = _query_entity("Tickets", filters)
    
    if "error" in result:
        return f"Error: {result['error']}\nDetails: {result.get('response_text', 'No details')}"
    
    items = result.get("items", [])
    if params.max_results:
        items = items[:params.max_results]
    
    return json.dumps({"count": len(items), "tickets": items}, indent=2)


@mcp.tool()
async def autotask_create_ticket(params: CreateTicketInput) -> str:
    """Create a new ticket in Autotask."""
    ticket_data = {
        "title": params.title,
        "companyID": params.company_id,
        "status": params.status,
        "priority": params.priority,
        "ticketType": params.ticket_type,
    }
    
    if params.description:
        ticket_data["description"] = params.description
    if params.queue_id:
        ticket_data["queueID"] = params.queue_id
    if params.assigned_resource_id:
        ticket_data["assignedResourceID"] = params.assigned_resource_id
    if params.assigned_resource_role_id:
        ticket_data["assignedResourceRoleID"] = params.assigned_resource_role_id
    if params.due_date_time:
        ticket_data["dueDateTime"] = params.due_date_time
    
    result = _make_request("POST", "Tickets", data=ticket_data)
    
    if "error" in result:
        return f"Error creating ticket: {result['error']}\nDetails: {result.get('response_text', 'No details')}"
    
    item = result.get("item", result)
    ticket_id = item.get("id", "unknown")
    return f"Ticket created successfully!\nTicket ID: {ticket_id}\n\nFull response:\n{json.dumps(item, indent=2)}"


@mcp.tool()
async def autotask_update_ticket(params: UpdateTicketInput) -> str:
    """
    Update an existing ticket in Autotask.
    
    Uses PATCH method to update only specified fields.
    Common status values: 1=New, 5=In Progress, 8=Waiting Customer, 5=Complete
    (Note: Status IDs vary by Autotask instance - use autotask_get_picklist_values to get exact values)
    """
    # First, get the current ticket to include required fields
    current = _make_request("GET", f"Tickets/{params.ticket_id}")
    if "error" in current:
        return f"Error fetching ticket: {current['error']}\nDetails: {current.get('response_text', 'No details')}"
    
    ticket = current.get("item", current)
    
    # Build update payload - must include id
    update_data = {"id": params.ticket_id}
    
    if params.title is not None:
        update_data["title"] = params.title
    if params.description is not None:
        update_data["description"] = params.description
    if params.status is not None:
        update_data["status"] = params.status
    if params.priority is not None:
        update_data["priority"] = params.priority
    if params.queue_id is not None:
        update_data["queueID"] = params.queue_id
    if params.assigned_resource_id is not None:
        update_data["assignedResourceID"] = params.assigned_resource_id
    if params.assigned_resource_role_id is not None:
        update_data["assignedResourceRoleID"] = params.assigned_resource_role_id
    if params.due_date_time is not None:
        update_data["dueDateTime"] = params.due_date_time
    
    result = _make_request("PATCH", "Tickets", data=update_data)
    
    if "error" in result:
        return f"Error updating ticket: {result['error']}\nDetails: {result.get('response_text', 'No details')}"
    
    item = result.get("item", result)
    return f"Ticket {params.ticket_id} updated successfully!\n\nUpdated fields:\n{json.dumps(update_data, indent=2)}\n\nFull response:\n{json.dumps(item, indent=2)}"


# =============================================================================
# TOOLS - TICKET NOTES
# =============================================================================

@mcp.tool()
async def autotask_create_ticket_note(params: CreateTicketNoteInput) -> str:
    """
    Create a note on a ticket in Autotask.
    
    Uses the /Tickets/{id}/Notes endpoint (parent-child pattern).
    
    Required fields:
    - ticketId: The ticket to add the note to
    - description: The note content
    - noteType: Type of note (picklist value)
    - publish: Visibility setting
    
    Common noteType values (vary by instance):
    - 1 = Ticket Detail / Task Detail
    - 2 = Resolution
    - 3 = Summary
    - 13 = System Workflow Note
    
    Common publish values:
    - 1 = All Autotask Users
    - 2 = Internal Only
    - 3 = Datto Internal
    
    Use autotask_get_picklist_values to get exact values for your instance.
    """
    note_data = {
        "description": params.description,
        "noteType": params.note_type,
        "publish": params.publish,
    }
    
    if params.title:
        note_data["title"] = params.title
    
    result = _make_request("POST", f"Tickets/{params.ticket_id}/Notes", data=note_data)
    
    if "error" in result:
        return f"Error creating ticket note: {result['error']}\nDetails: {result.get('response_text', 'No details')}\n\nRequest data:\n{json.dumps(note_data, indent=2)}"
    
    item = result.get("item", result)
    note_id = item.get("id", "unknown")
    return f"Ticket note created successfully!\nNote ID: {note_id}\nTicket ID: {params.ticket_id}\n\nFull response:\n{json.dumps(item, indent=2)}"


# =============================================================================
# TOOLS - TIME ENTRIES
# =============================================================================

@mcp.tool()
async def autotask_create_time_entry(params: CreateTimeEntryInput) -> str:
    """
    Create a time entry in Autotask.
    
    Uses the /TimeEntries endpoint.
    
    IMPORTANT REQUIREMENTS:
    1. Must have either ticketId OR taskId (not both, not neither)
    2. resourceId must be a valid, active resource
    3. roleId must be a valid role for the resource
    4. hoursWorked must be > 0 and <= 24
    5. summaryNotes is required for ticket time entries
    6. dateWorked defaults to today if not provided
    
    The API stores all times in UTC.
    
    Common issues:
    - 500 error often means missing/invalid required field
    - Role must be associated with the resource
    - Contract must be active and associated with the ticket's company
    """
    if not params.ticket_id and not params.task_id:
        return "Error: Either ticket_id or task_id is required"
    
    if params.ticket_id and params.task_id:
        return "Error: Provide either ticket_id OR task_id, not both"
    
    if params.hours_worked <= 0 or params.hours_worked > 24:
        return "Error: hours_worked must be > 0 and <= 24"
    
    # Build the time entry data
    time_entry_data = {
        "resourceID": params.resource_id,
        "roleID": params.role_id,
        "hoursWorked": params.hours_worked,
        "summaryNotes": params.summary_notes,
        "dateWorked": params.date_worked or _format_date_for_api(),
    }
    
    # Add ticket or task ID
    if params.ticket_id:
        time_entry_data["ticketID"] = params.ticket_id
    else:
        time_entry_data["taskID"] = params.task_id
    
    # Add optional fields
    if params.internal_notes:
        time_entry_data["internalNotes"] = params.internal_notes
    if params.billing_code_id:
        time_entry_data["billingCodeID"] = params.billing_code_id
    if params.contract_id:
        time_entry_data["contractID"] = params.contract_id
    if params.hours_to_bill is not None:
        time_entry_data["hoursToBill"] = params.hours_to_bill
    if params.is_non_billable is not None:
        time_entry_data["isNonBillable"] = params.is_non_billable
    if params.show_on_invoice is not None:
        time_entry_data["showOnInvoice"] = params.show_on_invoice
    if params.start_date_time:
        time_entry_data["startDateTime"] = params.start_date_time
    if params.end_date_time:
        time_entry_data["endDateTime"] = params.end_date_time
    
    result = _make_request("POST", "TimeEntries", data=time_entry_data)
    
    if "error" in result:
        return f"Error creating time entry: {result['error']}\nDetails: {result.get('response_text', 'No details')}\n\nRequest data:\n{json.dumps(time_entry_data, indent=2)}"
    
    item = result.get("item", result)
    entry_id = item.get("id", "unknown")
    return f"Time entry created successfully!\nTime Entry ID: {entry_id}\nHours: {params.hours_worked}\nTicket/Task: {params.ticket_id or params.task_id}\n\nFull response:\n{json.dumps(item, indent=2)}"


# =============================================================================
# TOOLS - COMPANIES
# =============================================================================

@mcp.tool()
async def autotask_search_companies(params: SearchCompaniesInput) -> str:
    """Search for companies in Autotask."""
    filters = []
    
    if params.name_contains:
        filters.append({"field": "companyName", "op": "contains", "value": params.name_contains})
    if params.is_active is not None:
        filters.append({"field": "isActive", "op": "eq", "value": params.is_active})
    
    if not filters:
        filters.append({"field": "isActive", "op": "eq", "value": True})
    
    result = _query_entity("Companies", filters)
    
    if "error" in result:
        return f"Error: {result['error']}\nDetails: {result.get('response_text', 'No details')}"
    
    items = result.get("items", [])
    if params.max_results:
        items = items[:params.max_results]
    
    return json.dumps({"count": len(items), "companies": items}, indent=2)


@mcp.tool()
async def autotask_get_company(params: GetCompanyInput) -> str:
    """Get a company by ID from Autotask."""
    result = _make_request("GET", f"Companies/{params.company_id}")
    
    if "error" in result:
        return f"Error: {result['error']}\nDetails: {result.get('response_text', 'No details')}"
    
    company = result.get("item", result)
    return json.dumps(company, indent=2)


# =============================================================================
# TOOLS - CONTACTS
# =============================================================================

@mcp.tool()
async def autotask_search_contacts(params: SearchContactsInput) -> str:
    """Search for contacts in Autotask."""
    filters = []
    
    if params.company_id:
        filters.append({"field": "companyID", "op": "eq", "value": params.company_id})
    if params.email_contains:
        filters.append({"field": "emailAddress", "op": "contains", "value": params.email_contains})
    if params.first_name:
        filters.append({"field": "firstName", "op": "contains", "value": params.first_name})
    if params.last_name:
        filters.append({"field": "lastName", "op": "contains", "value": params.last_name})
    
    if not filters:
        filters.append({"field": "isActive", "op": "eq", "value": 1})
    
    result = _query_entity("Contacts", filters)
    
    if "error" in result:
        return f"Error: {result['error']}\nDetails: {result.get('response_text', 'No details')}"
    
    items = result.get("items", [])
    if params.max_results:
        items = items[:params.max_results]
    
    return json.dumps({"count": len(items), "contacts": items}, indent=2)


# =============================================================================
# TOOLS - RESOURCES
# =============================================================================

@mcp.tool()
async def autotask_search_resources(params: SearchResourcesInput) -> str:
    """Search for resources (users/technicians) in Autotask."""
    filters = []
    
    if params.first_name:
        filters.append({"field": "firstName", "op": "contains", "value": params.first_name})
    if params.last_name:
        filters.append({"field": "lastName", "op": "contains", "value": params.last_name})
    if params.email:
        filters.append({"field": "email", "op": "contains", "value": params.email})
    if params.is_active is not None:
        filters.append({"field": "isActive", "op": "eq", "value": params.is_active})
    
    if not filters:
        filters.append({"field": "isActive", "op": "eq", "value": True})
    
    result = _query_entity("Resources", filters)
    
    if "error" in result:
        return f"Error: {result['error']}\nDetails: {result.get('response_text', 'No details')}"
    
    items = result.get("items", [])
    if params.max_results:
        items = items[:params.max_results]
    
    return json.dumps({"count": len(items), "resources": items}, indent=2)


@mcp.tool()
async def autotask_get_resource(params: GetResourceInput) -> str:
    """Get a resource by ID from Autotask."""
    result = _make_request("GET", f"Resources/{params.resource_id}")
    
    if "error" in result:
        return f"Error: {result['error']}\nDetails: {result.get('response_text', 'No details')}"
    
    resource = result.get("item", result)
    return json.dumps(resource, indent=2)


# =============================================================================
# TOOLS - PICKLIST VALUES
# =============================================================================

@mcp.tool()
async def autotask_get_picklist_values(params: GetPicklistValuesInput) -> str:
    """
    Get picklist values for a field in Autotask.
    
    Use this to discover valid values for fields like:
    - Tickets/status
    - Tickets/priority
    - Tickets/ticketType
    - Tickets/queueID
    - TicketNotes/noteType
    - TicketNotes/publish
    - TimeEntries/type
    
    Example: entity="Tickets", field="status"
    """
    result = _make_request("GET", f"{params.entity}/entityInformation/fields")
    
    if "error" in result:
        return f"Error: {result['error']}\nDetails: {result.get('response_text', 'No details')}"
    
    fields = result.get("fields", [])
    
    # Find the specific field
    target_field = None
    for field in fields:
        if field.get("name", "").lower() == params.field.lower():
            target_field = field
            break
    
    if not target_field:
        available_fields = [f.get("name") for f in fields if f.get("isPickList")]
        return f"Field '{params.field}' not found in {params.entity}.\n\nAvailable picklist fields:\n{json.dumps(available_fields, indent=2)}"
    
    if not target_field.get("isPickList"):
        return f"Field '{params.field}' is not a picklist field."
    
    picklist_values = target_field.get("picklistValues", [])
    return f"Picklist values for {params.entity}/{params.field}:\n\n{json.dumps(picklist_values, indent=2)}"


# =============================================================================
# TOOLS - ROLES (needed for time entries)
# =============================================================================

class SearchRolesInput(BaseModel):
    """Input for searching roles."""
    is_active: Optional[bool] = Field(True, description="Filter by active status")
    max_results: Optional[int] = Field(50, description="Maximum number of results")


@mcp.tool()
async def autotask_search_roles(params: SearchRolesInput) -> str:
    """
    Search for roles in Autotask.
    
    Roles are required when creating time entries.
    The role must be valid for the resource creating the time entry.
    """
    filters = []
    
    if params.is_active is not None:
        filters.append({"field": "isActive", "op": "eq", "value": params.is_active})
    
    if not filters:
        filters.append({"field": "isActive", "op": "eq", "value": True})
    
    result = _query_entity("Roles", filters)
    
    if "error" in result:
        return f"Error: {result['error']}\nDetails: {result.get('response_text', 'No details')}"
    
    items = result.get("items", [])
    if params.max_results:
        items = items[:params.max_results]
    
    return json.dumps({"count": len(items), "roles": items}, indent=2)


# =============================================================================
# COMBINED HELPER TOOLS
# =============================================================================

class UpdateTicketStatusAndNoteInput(BaseModel):
    """Input for updating ticket status and adding a note in one operation."""
    ticket_id: int = Field(..., description="The ticket ID to update")
    status: int = Field(..., description="New status ID")
    note_description: str = Field(..., description="Note to add explaining the status change")
    note_type: int = Field(1, description="Note type ID (default: 1)")
    publish: int = Field(1, description="Note publish setting (default: 1 = All Autotask Users)")


@mcp.tool()
async def autotask_update_ticket_status_with_note(params: UpdateTicketStatusAndNoteInput) -> str:
    """
    Update a ticket's status and add a note in one operation.
    
    This is a convenience tool that:
    1. Updates the ticket status
    2. Adds a note explaining the change
    
    Common status values (vary by instance - use autotask_get_picklist_values):
    - 1 = New
    - 5 = In Progress
    - 8 = Waiting Customer
    - Complete (varies)
    """
    results = []
    
    # Step 1: Update ticket status
    update_data = {"id": params.ticket_id, "status": params.status}
    status_result = _make_request("PATCH", "Tickets", data=update_data)
    
    if "error" in status_result:
        results.append(f"❌ Status update failed: {status_result['error']}\nDetails: {status_result.get('response_text', 'No details')}")
    else:
        results.append(f"✅ Status updated to {params.status}")
    
    # Step 2: Add note
    note_data = {
        "ticketID": params.ticket_id,
        "description": params.note_description,
        "noteType": params.note_type,
        "publish": params.publish,
    }
    note_result = _make_request("POST", f"Tickets/{params.ticket_id}/Notes", data=note_data)
    
    if "error" in note_result:
        results.append(f"❌ Note creation failed: {note_result['error']}\nDetails: {note_result.get('response_text', 'No details')}")
    else:
        note_id = note_result.get("item", {}).get("id", "unknown")
        results.append(f"✅ Note added (ID: {note_id})")
    
    return f"Ticket {params.ticket_id} update results:\n\n" + "\n".join(results)


class LogTimeAndUpdateStatusInput(BaseModel):
    """Input for logging time and optionally updating status."""
    ticket_id: int = Field(..., description="The ticket ID")
    resource_id: int = Field(..., description="Resource ID who performed the work")
    role_id: int = Field(..., description="Role ID for the resource")
    hours_worked: float = Field(..., description="Hours worked")
    summary_notes: str = Field(..., description="Summary of work performed")
    new_status: Optional[int] = Field(None, description="Optionally update ticket status")
    date_worked: Optional[str] = Field(None, description="Date worked (defaults to today)")


@mcp.tool()
async def autotask_log_time_and_update_status(params: LogTimeAndUpdateStatusInput) -> str:
    """
    Log time to a ticket and optionally update its status.
    
    This is a convenience tool that:
    1. Creates a time entry for the ticket
    2. Optionally updates the ticket status
    
    Requires:
    - Valid resource_id
    - Valid role_id (must be associated with the resource)
    - hours_worked > 0 and <= 24
    """
    results = []
    
    # Step 1: Create time entry
    time_entry_data = {
        "ticketID": params.ticket_id,
        "resourceID": params.resource_id,
        "roleID": params.role_id,
        "hoursWorked": params.hours_worked,
        "summaryNotes": params.summary_notes,
        "dateWorked": params.date_worked or _format_date_for_api(),
    }
    
    time_result = _make_request("POST", "TimeEntries", data=time_entry_data)
    
    if "error" in time_result:
        results.append(f"❌ Time entry failed: {time_result['error']}\nDetails: {time_result.get('response_text', 'No details')}\n\nRequest data:\n{json.dumps(time_entry_data, indent=2)}")
    else:
        entry_id = time_result.get("item", {}).get("id", "unknown")
        results.append(f"✅ Time entry created (ID: {entry_id}) - {params.hours_worked} hours")
    
    # Step 2: Update status if requested
    if params.new_status is not None:
        update_data = {"id": params.ticket_id, "status": params.new_status}
        status_result = _make_request("PATCH", "Tickets", data=update_data)
        
        if "error" in status_result:
            results.append(f"❌ Status update failed: {status_result['error']}\nDetails: {status_result.get('response_text', 'No details')}")
        else:
            results.append(f"✅ Status updated to {params.new_status}")
    
    return f"Ticket {params.ticket_id} operations:\n\n" + "\n".join(results)


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    # Validate configuration
    if not all([AUTOTASK_USERNAME, AUTOTASK_SECRET, AUTOTASK_INTEGRATION_CODE]):
        print("Warning: Autotask credentials not fully configured.")
        print("Please set the following environment variables:")
        print("  - AUTOTASK_USERNAME")
        print("  - AUTOTASK_SECRET")
        print("  - AUTOTASK_INTEGRATION_CODE")
        print("  - AUTOTASK_API_URL (optional, defaults to webservices16)")
    
    mcp.run()