
import gspread
from gspread import Worksheet
from gspread.utils import ValueInputOption
import logging
from datetime import datetime, timedelta
import os
import asyncio
import json

logger = logging.getLogger(__name__)

class GoogleSheetsManager:
    def __init__(self):
        self.client = None
        self.spreadsheet = None
        self.worksheet = None
        self.initialized = False
        self._initialize()

    def _initialize(self):
        """Initialize Google Sheets connection"""
        try:
            # Get environment variables
            google_credentials = os.getenv('GOOGLE_CREDENTIALS')
            sheet_id = os.getenv('SHEET_ID')
            
            if not google_credentials or not sheet_id:
                logger.error("❌ GOOGLE_CREDENTIALS or SHEET_ID not found in environment")
                return

            # Parse JSON credentials
            creds_dict = json.loads(google_credentials)
            
            # Initialize client
            from google.oauth2.service_account import Credentials
            scopes = ['https://www.googleapis.com/auth/spreadsheets']
            credentials = Credentials.from_service_account_info(creds_dict, scopes=scopes)
            
            self.client = gspread.authorize(credentials)
            self.spreadsheet = self.client.open_by_key(sheet_id)
            
            # Try to find worksheet
            try:
                self.worksheet = self.spreadsheet.worksheet('Смены')
            except gspread.WorksheetNotFound:
                # Create new worksheet if doesn't exist
                self.worksheet = self.spreadsheet.add_worksheet(title='Смены', rows=1000, cols=10)
                # Add headers
                self.worksheet.update('A1:G1', [['Дата', 'Начало', 'Конец', 'Выручка', 'Чаевые', 'Часы', 'Прибыль']])
            
            self.initialized = True
            logger.info("✅ Google Sheets initialized successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize Google Sheets: {e}")
            self.initialized = False

    def _calculate_hours(self, start_time, end_time):
        """Calculate hours between start and end time"""
        try:
            start = datetime.strptime(start_time, "%H:%M")
            end = datetime.strptime(end_time, "%H:%M")

            
            # Handle overnight shifts
            if end < start:
                end += timedelta(days=1)
            
            duration = end - start
            hours = duration.total_seconds() / 3600
            return hours
        except Exception as e:
            logger.error(f"❌ Error calculating hours: {e}")
            return 0

    def _calculate_profit(self, start_time, end_time, revenue, tips):
        """Calculate profit using formula: (hours * 220) + tips + (revenue * 0.015)"""
        try:
            hours = self._calculate_hours(start_time, end_time)
            hourly_rate = 220
            revenue_percentage = 0.015
            
            # Convert to numbers
            revenue_val = float(str(revenue).replace(',', '.')) if revenue else 0
            tips_val = float(str(tips).replace(',', '.')) if tips else 0
            
            profit = (hours * hourly_rate) + tips_val + (revenue_val * revenue_percentage)
            logger.info(f"💰 Profit calculation: ({hours}h * {hourly_rate}) + {tips_val} + ({revenue_val} * {revenue_percentage}) = {profit}")
            return profit
        except Exception as e:
            logger.error(f"❌ Error calculating profit: {e}")
            return 0

    async def add_shift(self, date_msg, start, end):
        """Add shift to spreadsheet"""
        if not self.initialized:
            logger.error("Google Sheets not initialized")
            return False

        try:
            # Validate date
            date_obj = datetime.strptime(date_msg, "%d.%m.%Y").date()
            formatted_date = date_obj.strftime("%d.%m.%Y")
            
            # Validate time
            datetime.strptime(start, "%H:%M")
            datetime.strptime(end, "%H:%M")
            
            # Find existing record
            try:
                cell = await asyncio.to_thread(self.worksheet.find, formatted_date)
                if cell:
                    # Update existing record
                    row = cell.row
                    await asyncio.to_thread(
                        self.worksheet.update,
                        f'B{row}:C{row}',
                        [[start, end]],
                        value_input_option=ValueInputOption.user_entered
                    )
                    
                    # Recalculate profit
                    revenue_cell = await asyncio.to_thread(self.worksheet.cell, row, 4)
                    tips_cell = await asyncio.to_thread(self.worksheet.cell, row, 5)
                    
                    revenue = revenue_cell.value if revenue_cell.value else "0"
                    tips = tips_cell.value if tips_cell.value else "0"
                    
                    profit = self._calculate_profit(start, end, revenue, tips)
                    await asyncio.to_thread(
                        self.worksheet.update,
                        f'G{row}',
                        [[profit]],
                        value_input_option=ValueInputOption.user_entered
                    )
                    
                    logger.info(f"📝 Updated existing shift: {formatted_date}")
                else:
                    # Add new record
                    profit = self._calculate_profit(start, end, 0, 0)
                    new_row = [formatted_date, start, end, '', '', profit]
                    await asyncio.to_thread(
                        self.worksheet.append_row,
                        new_row,
                        value_input_option=ValueInputOption.user_entered
                    )
                    logger.info(f"✅ Added new shift: {formatted_date}")
                
                return True
                
            except Exception as e:
                logger.error(f"❌ Error in sheet operation: {e}")
                return False
                
        except ValueError as e:
            logger.error(f"❌ Invalid date/time format: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Error adding shift: {e}")
            return False

    async def update_value(self, date_msg, field, value):
        """Update value in spreadsheet"""
        if not self.initialized:
            logger.error("Google Sheets not initialized")
            return False

        try:
            date_obj = datetime.strptime(date_msg, "%d.%m.%Y").date()
            formatted_date = date_obj.strftime("%d.%m.%Y")
            
            # Find date
            cell = await asyncio.to_thread(self.worksheet.find, formatted_date)
            if not cell:
                logger.warning(f"Date not found: {formatted_date}")
                return False

            row = cell.row
            column_mapping = {
                'начало': 'B',
                'конец': 'C', 
                'выручка': 'D',
                'чай': 'E',
                'часы': F,
                'Прибыль' G
            }
            
            column = column_mapping.get(field.lower())
            if not column:
                logger.error(f"Unknown field: {field}")
                return False

            await asyncio.to_thread(
                self.worksheet.update,
                f'{column}{row}',
                [[value]],
                value_input_option=ValueInputOption.user_entered
            )
            
            # Recalculate profit after update
            start_cell = await asyncio.to_thread(self.worksheet.cell, row, 2)  # Column B
            end_cell = await asyncio.to_thread(self.worksheet.cell, row, 3)    # Column C
            revenue_cell = await asyncio.to_thread(self.worksheet.cell, row, 4) # Column D
            tips_cell = await asyncio.to_thread(self.worksheet.cell, row, 5)   # Column E
            hours = await asyncio.to_thread(self.worksheet.cell, row, 6) # Column F
            
            start_time = start_cell.value if start_cell.value else "00:00"
            end_time = end_cell.value if end_cell.value else "00:00"
            revenue = revenue_cell.value if revenue_cell.value else "0"
            tips = tips_cell.value if tips_cell.value else "0"
            
            profit = self._calculate_profit(start_time, end_time, revenue, tips)
            await asyncio.to_thread(
                self.worksheet.update,
                f'F{row}',
                [[profit]],
                value_input_option=ValueInputOption.user_entered
            )
            
            logger.info(f"✅ Updated {field} for {formatted_date} and recalculated profit: {profit}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error updating value: {e}")
            return False

    async def get_profit(self, date_msg):
        """Get profit for date using new formula"""
        if not self.initialized:
            logger.error("Google Sheets not initialized")
            return None

        try:
            date_obj = datetime.strptime(date_msg, "%d.%m.%Y").date()
            formatted_date = date_obj.strftime("%d.%m.%Y")
            
            cell = await asyncio.to_thread(self.worksheet.find, formatted_date)
            if not cell:
                return None

            row = cell.row
            
            # Get all values
            start_cell = await asyncio.to_thread(self.worksheet.cell, row, 2)  # Column B
            end_cell = await asyncio.to_thread(self.worksheet.cell, row, 3)    # Column C
            revenue_cell = await asyncio.to_thread(self.worksheet.cell, row, 4) # Column D
            tips_cell = await asyncio.to_thread(self.worksheet.cell, row, 5)   # Column E
            hours = await asyncio.to_thread(self.worksheet.cell, row, 6) # Column F
            profit_cell = await asyncio.to_thread(self.worksheet.cell, row, 7) # Column G
            
            start_time = start_cell.value if start_cell.value else "00:00"
            end_time = end_cell.value if end_cell.value else "00:00"
            revenue = revenue_cell.value if revenue_cell.value else "0"
            tips = tips_cell.value if tips_cell.value else "0"
            hours = hours .value if hours.value else "00:00"
            existing_profit = profit_cell.value if profit_cell.value else "0"
            
            # Calculate profit using new formula
            profit = self._calculate_profit(start_time, end_time, revenue, tips)
            
            # Update profit cell if different
            if abs(float(existing_profit.replace(',', '.')) - profit) > 0.01:
                await asyncio.to_thread(
                    self.worksheet.update,
                    g'G{row}',
                    [[profit]],
                    value_input_option=ValueInputOption.user_entered
                )
                logger.info(f"📝 Updated profit calculation for {formatted_date}: {profit}")
            
            return str(profit)
                
        except Exception as e:
            logger.error(f"❌ Error getting profit: {e}")
            return None

    async def check_shift_exists(self, date_msg):
        """Check if shift exists"""
        if not self.initialized:
            logger.error("Google Sheets not initialized")
            return False

        try:
            date_obj = datetime.strptime(date_msg, "%d.%m.%Y").date()
            formatted_date = date_obj.strftime("%d.%m.%Y")
            
            cell = await asyncio.to_thread(self.worksheet.find, formatted_date)
            return cell is not None
            
        except Exception as e:
            logger.error(f"❌ Error checking shift existence: {e}")
            return False

# Global instance
sheets_manager = GoogleSheetsManager()

# Functions for backward compatibility
async def add_shift(date_msg, start, end):
    return await sheets_manager.add_shift(date_msg, start, end)

async def update_value(date_msg, field, value):
    return await sheets_manager.update_value(date_msg, field, value)

async def get_profit(date_msg):
    return await sheets_manager.get_profit(date_msg)

async def check_shift_exists(date_msg):
    return await sheets_manager.check_shift_exists(date_msg)
