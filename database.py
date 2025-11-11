import sqlite3
import logging
from datetime import datetime
import json
import os

logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self, db_path='shifts.db'):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize database"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS shifts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        date TEXT UNIQUE NOT NULL,
                        start_time TEXT NOT NULL,
                        end_time TEXT NOT NULL,
                        revenue REAL DEFAULT 0,
                        tips REAL DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Create index for fast date search
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_date ON shifts(date)
                ''')
                
                conn.commit()
            logger.info("✅ SQLite database initialized")
        except Exception as e:
            logger.error(f"❌ Database initialization error: {e}")

    def _get_connection(self):
        """Get database connection"""
        return sqlite3.connect(self.db_path)

    async def add_shift(self, date_msg, start, end):
        """Add shift to database"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO shifts (date, start_time, end_time, updated_at)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ''', (date_msg, start, end))
                conn.commit()
            
            logger.info(f"✅ Shift added to database: {date_msg}")
            return True
        except Exception as e:
            logger.error(f"❌ Error adding shift to database: {e}")
            return False

    async def update_value(self, date_msg, field, value):
        """Update value in database"""
        try:
            field_mapping = {
                'начало': 'start_time',
                'конец': 'end_time',
                'выручка': 'revenue',
                'чай': 'tips'
            }
            
            db_field = field_mapping.get(field.lower())
            if not db_field:
                logger.error(f"❌ Unknown field: {field}")
                return False

            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                if db_field in ['revenue', 'tips']:
                    # For numeric fields
                    try:
                        numeric_value = float(value)
                    except ValueError:
                        logger.error(f"❌ Invalid numeric value: {value}")
                        return False
                    
                    cursor.execute(f'''
                        UPDATE shifts SET {db_field} = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE date = ?
                    ''', (numeric_value, date_msg))
                else:
                    # For text fields
                    cursor.execute(f'''
                        UPDATE shifts SET {db_field} = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE date = ?
                    ''', (value, date_msg))
                
                if cursor.rowcount == 0:
                    logger.warning(f"❌ No shift found for date: {date_msg}")
                    return False
                
                conn.commit()
            
            logger.info(f"✅ Updated {field} for {date_msg} in database")
            return True
        except Exception as e:
            logger.error(f"❌ Error updating value in database: {e}")
            return False

    async def get_profit(self, date_msg):
        """Get profit from database"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT revenue, tips FROM shifts WHERE date = ?
                ''', (date_msg,))
                
                result = cursor.fetchone()
                if not result:
                    return None
                
                revenue, tips = result
                profit = (revenue or 0) + (tips or 0)
                return str(profit)
                
        except Exception as e:
            logger.error(f"❌ Error getting profit from database: {e}")
            return None

    async def check_shift_exists(self, date_msg):
        """Check if shift exists"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT 1 FROM shifts WHERE date = ?
                ''', (date_msg,))
                
                return cursor.fetchone() is not None
                
        except Exception as e:
            logger.error(f"❌ Error checking shift existence: {e}")
            return False

    async def get_shifts_in_period(self, start_date, end_date):
        """Get shifts for period"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT date, start_time, end_time, revenue, tips 
                    FROM shifts 
                    WHERE date BETWEEN ? AND ?
                    ORDER BY date
                ''', (start_date, end_date))
                
                shifts = []
                for row in cursor.fetchall():
                    shifts.append({
                        'date': row[0],
                        'start': row[1],
                        'end': row[2],
                        'revenue': row[3] or 0,
                        'tips': row[4] or 0
                    })
                
                return shifts
        except Exception as e:
            logger.error(f"❌ Error getting shifts in period: {e}")
            return []

    async def get_statistics(self, start_date, end_date):
        """Get statistics for period"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT 
                        COUNT(*) as shift_count,
                        SUM(revenue) as total_revenue,
                        SUM(tips) as total_tips,
                        AVG(revenue) as avg_revenue,
                        AVG(tips) as avg_tips
                    FROM shifts 
                    WHERE date BETWEEN ? AND ?
                ''', (start_date, end_date))
                
                result = cursor.fetchone()
                if not result or not result[0]:
                    return None
                
                return {
                    'shift_count': result[0],
                    'total_revenue': result[1] or 0,
                    'total_tips': result[2] or 0,
                    'total_profit': (result[1] or 0) + (result[2] or 0),
                    'avg_revenue': result[3] or 0,
                    'avg_tips': result[4] or 0,
                    'avg_profit': (result[3] or 0) + (result[4] or 0)
                }
        except Exception as e:
            logger.error(f"❌ Error getting statistics: {e}")
            return None

# Global instance
db_manager = DatabaseManager()


