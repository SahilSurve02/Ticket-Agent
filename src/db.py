import sqlite3
import json
import os
from datetime import datetime
from typing import Dict, Optional, List

# Database file path
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "tickets.db")

def get_db_connection():
    """Create a database connection"""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Access columns by name
    return conn

_db_initialized = False

def init_db():
    """Initialize the database schema"""
    global _db_initialized
    
    # Skip if already initialized in this process
    if _db_initialized:
        return
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create tickets table
    # We store core query fields separately and the full object in 'ticket_data'
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS tickets (
        ticket_id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        category TEXT,
        priority TEXT,
        status TEXT DEFAULT 'Open',
        created_at TIMESTAMP,
        ticket_data TEXT  -- Stores the full JSON blob
    )
    ''')
    
    # Create index for duplicate checking (improves performance)
    cursor.execute('''
    CREATE INDEX IF NOT EXISTS idx_user_category_status 
    ON tickets(user_id, category, status)
    ''')
    
    conn.commit()
    conn.close()
    
    _db_initialized = True
    print(f"[DATABASE] SQLite initialized at {DB_PATH}")

def save_ticket(ticket_dict: Dict) -> bool:
    """Save a new ticket to the database"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
        INSERT INTO tickets (ticket_id, user_id, category, priority, status, created_at, ticket_data)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            ticket_dict["ticket_id"],
            ticket_dict.get("user_id"),
            ticket_dict.get("category"),
            ticket_dict.get("priority"),
            "Open",
            datetime.now().isoformat(),
            json.dumps(ticket_dict)
        ))
        
        conn.commit()
        return True
    except Exception as e:
        print(f"[DATABASE ERROR] Failed to save ticket: {e}")
        return False
    finally:
        if conn:
            conn.close()

def check_for_duplicate_ticket(user_id: str, category: str) -> bool:
    """
    Check if the user has an open ticket in the same category.
    Returns True if a duplicate exists.
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT count(*) FROM tickets 
        WHERE user_id = ? 
        AND category = ? 
        AND status != 'Closed'
        ''', (user_id, category))
        
        count = cursor.fetchone()[0]
        return count > 0
    except Exception as e:
        print(f"[DATABASE ERROR] Check duplicate failed: {e}")
        return False
    finally:
        if conn:
            conn.close()


def get_ticket_by_id(ticket_id: str) -> Optional[Dict]:
    """
    Retrieve a ticket by its ID.
    Returns the full ticket dictionary or None if not found.
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT ticket_data FROM tickets WHERE ticket_id = ?', (ticket_id,))
        row = cursor.fetchone()
        
        if row:
            return json.loads(row['ticket_data'])
        return None
    except Exception as e:
        print(f"[DATABASE ERROR] Failed to retrieve ticket: {e}")
        return None
    finally:
        if conn:
            conn.close()


def get_user_tickets(user_id: str, status: Optional[str] = None) -> List[Dict]:
    """
    Retrieve all tickets for a specific user.
    Optionally filter by status (e.g., 'Open', 'Closed').
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if status:
            cursor.execute(
                'SELECT ticket_data FROM tickets WHERE user_id = ? AND status = ? ORDER BY created_at DESC',
                (user_id, status)
            )
        else:
            cursor.execute(
                'SELECT ticket_data FROM tickets WHERE user_id = ? ORDER BY created_at DESC',
                (user_id,)
            )
        
        rows = cursor.fetchall()
        return [json.loads(row['ticket_data']) for row in rows]
    except Exception as e:
        print(f"[DATABASE ERROR] Failed to retrieve user tickets: {e}")
        return []
    finally:
        if conn:
            conn.close()


def update_ticket_status(ticket_id: str, new_status: str) -> bool:
    """
    Update the status of a ticket (e.g., from 'Open' to 'Closed').
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Update both the status column and the JSON data
        cursor.execute('SELECT ticket_data FROM tickets WHERE ticket_id = ?', (ticket_id,))
        row = cursor.fetchone()
        
        if not row:
            print(f"[DATABASE ERROR] Ticket {ticket_id} not found")
            return False
        
        ticket_data = json.loads(row['ticket_data'])
        ticket_data['status'] = new_status
        
        cursor.execute(
            'UPDATE tickets SET status = ?, ticket_data = ? WHERE ticket_id = ?',
            (new_status, json.dumps(ticket_data), ticket_id)
        )
        
        conn.commit()
        return True
    except Exception as e:
        print(f"[DATABASE ERROR] Failed to update ticket status: {e}")
        return False
    finally:
        if conn:
            conn.close()


def get_all_tickets(limit: Optional[int] = None) -> List[Dict]:
    """
    Retrieve all tickets from the database.
    Optionally limit the number of results.
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if limit:
            cursor.execute(
                'SELECT ticket_data FROM tickets ORDER BY created_at DESC LIMIT ?',
                (limit,)
            )
        else:
            cursor.execute('SELECT ticket_data FROM tickets ORDER BY created_at DESC')
        
        rows = cursor.fetchall()
        return [json.loads(row['ticket_data']) for row in rows]
    except Exception as e:
        print(f"[DATABASE ERROR] Failed to retrieve tickets: {e}")
        return []
    finally:
        if conn:
            conn.close()