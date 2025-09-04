// --- CONSTANTS ---
const MASTER_LIST_SHEET_NAME = 'Master List';
const SALES_SHEET_NAME = 'Sales Data';
const LOGIN_SHEET_NAME = 'Login';
const SERVICE_SHEET_NAME = 'Service';
const CREDENTIALS_SHEET_NAME = 'Credentials';
const MASTER_SHEET_NAME = 'Master List'; // Add this line
const HOURS_SHEET_NAME = 'Hours';
const SPREADSHEET_ID = '1rk02i4TGZQHm3o0wK8umABZgmnQQNN3zNaD9n0XIsMo';
// Master password - make sure this is set correctly
const MASTER_PASSWORD = 'test'; // Replace with your actual master password

/**
 * Serves the web app HTML.
 * @param {Object} e The event parameter (not used).
 * @return {HtmlOutput} The HTML content to display.
 */
function doGet(e) {
  // Initialize the master password
  initializeMasterPassword();
  
  return HtmlService.createHtmlOutputFromFile('InventoryApp')
    .setTitle('VEND LAS VEGAS Inventory Portal')
    .setFaviconUrl('https://i.imgur.com/lfcgQ0s.png')
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
}

// Make sure this function is defined and accessible
function getSpreadsheet() {
  try {
    return SpreadsheetApp.openById(SPREADSHEET_ID);
  } catch (error) {
    console.error('Error opening spreadsheet:', error);
    throw new Error('Could not access spreadsheet. Please check the spreadsheet ID.');
  }
}

/**
 * Handles POST requests from the web app
 * @param {Object} e The event parameter containing POST data
 * @return {ContentService} JSON response
 */
function doPost(e) {
  try {
    const data = JSON.parse(e.postData.contents);
    const action = data.action;
    
    if (action === 'generatePDF') {
      try {
        const pdfBlob = exportInventoryStatusToHTMLPDF();
        
        // Convert to base64 for web delivery
        const base64Data = Utilities.base64Encode(pdfBlob.getBytes());
        
        return ContentService
          .createTextOutput(JSON.stringify({
            success: true,
            pdfData: base64Data,
            fileName: pdfBlob.getName() || 'Inventory_Status_Report.pdf',
            mimeType: 'application/pdf'
          }))
          .setMimeType(ContentService.MimeType.JSON);
          
      } catch (error) {
        console.error('PDF generation error:', error);
        return ContentService
          .createTextOutput(JSON.stringify({
            success: false,
            error: 'Failed to generate PDF: ' + error.message
          }))
          .setMimeType(ContentService.MimeType.JSON);
      }
    }
    
    // Handle other actions here if needed
    else {
      return ContentService
        .createTextOutput(JSON.stringify({
          success: false,
          error: 'Unknown action: ' + action
        }))
        .setMimeType(ContentService.MimeType.JSON);
    }
    
  } catch (error) {
    console.error('Error in doPost:', error);
    return ContentService
      .createTextOutput(JSON.stringify({
        success: false,
        error: 'Server error: ' + error.message
      }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}


/**
 * Gets the machine ID from the Credentials sheet.
 * @return {string} The machine ID.
 */
function getMachineID() {
  try {
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const sheet = ss.getSheetByName(CREDENTIALS_SHEET_NAME);
    
    if (!sheet) {
      console.error('Credentials sheet not found.');
      return 'Sheet Not Found';
    }
    
    // Get the machine ID from cell B16
    const machineID = sheet.getRange('B16').getValue();
    console.log('Machine ID from sheet:', machineID);
    
    return machineID || 'Not Set';
  } catch (e) {
    console.error('Error getting machine ID:', e);
    return 'Error: ' + e.message;
  }
}


/**
 * Checks the login credentials from the web app.
 * @param {string} username The username entered by the user.
 * @param {string} password The password entered by the user.
 * @return {boolean} True if the login is successful, false otherwise.
 */
function checkLogin(username, password) {
  try {
    console.log(`=== LOGIN ATTEMPT ===`);
    console.log(`Received username: "${username}" (type: ${typeof username})`);
    console.log(`Received password: "${password}" (type: ${typeof password})`);
    console.log(`Master password: "${MASTER_PASSWORD}" (type: ${typeof MASTER_PASSWORD})`);
    
    if (!username || !password) {
      console.log('Username or password is empty');
      return false;
    }
    
    // 1. Check against the master password first.
    console.log('Checking against master password...');
    if (String(password).trim() === String(MASTER_PASSWORD).trim()) {
      console.log('✓ Login successful with master password.');
      return true;
    } else {
      console.log('✗ Master password does not match');
    }

    // 2. If not the master password, check the Login sheet.
    console.log('Checking Login sheet...');
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const loginSheet = ss.getSheetByName(LOGIN_SHEET_NAME);
    
    if (!loginSheet) {
      console.error('Login sheet not found. Available sheets:', ss.getSheets().map(s => s.getName()));
      return false;
    }
    
    console.log('Login sheet found successfully');
    const data = loginSheet.getDataRange().getValues();
    console.log(`Login sheet has ${data.length} rows`);
    console.log('First few rows of data:', data.slice(0, 3));
    
    // Start from row 2 (index 1) to ignore headers.
    for (let i = 1; i < data.length; i++) {
      if (data[i].length >= 2 && data[i][0] && data[i][1]) {
        const sheetUsername = String(data[i][0]).trim();
        const sheetPassword = String(data[i][1]).trim();
        
        console.log(`Row ${i+1}: Username="${sheetUsername}", Password="${sheetPassword}"`);
        
        if (sheetUsername === String(username).trim() && sheetPassword === String(password).trim()) {
          console.log(`✓ Login successful for user: ${username}`);
          return true;
        }
      }
    }

    console.log(`✗ Login failed for user: ${username}`);
    return false;
  } catch (e) {
    console.error('Error in checkLogin:', e);
    console.error('Error stack:', e.stack);
    return false;
  }
}

/**
 * Test function to check sheet names - REMOVE THIS AFTER TESTING
 */
function testSheetNames() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheets = ss.getSheets();
  
  console.log('Available sheets:');
  sheets.forEach(sheet => {
    console.log(`- "${sheet.getName()}"`);
  });
  
  console.log('Looking for LOGIN_SHEET_NAME:', LOGIN_SHEET_NAME);
  const loginSheet = ss.getSheetByName(LOGIN_SHEET_NAME);
  console.log('Login sheet found:', loginSheet ? 'Yes' : 'No');
  
  if (loginSheet) {
    const data = loginSheet.getDataRange().getValues();
    console.log('Login sheet data:', data);
  }
}

/**
 * Test function to check master password - REMOVE THIS AFTER TESTING
 */
function testMasterPassword() {
  console.log('Master password is set to:', MASTER_PASSWORD);
  console.log('Master password type:', typeof MASTER_PASSWORD);
  console.log('Master password length:', MASTER_PASSWORD ? MASTER_PASSWORD.length : 'undefined');
  
  // Test the login function directly
  const testResult = checkLogin('test', MASTER_PASSWORD);
  console.log('Direct test result:', testResult);
}




/**
 * Logs a user action to the Service sheet.
 * @param {string} username The username.
 * @param {string} description The action description.
 */
function logUserAction(username, description) {
  try {
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const serviceSheet = ss.getSheetByName(SERVICE_SHEET_NAME);
    
    if (!serviceSheet) {
      console.error('Service sheet not found.');
      return;
    }
    
    const timestamp = new Date();
    serviceSheet.appendRow([timestamp, username, description]);
  } catch (e) {
    console.error('Error logging user action:', e);
  }
}

/**
 * Gets the list of users from the Login sheet.
 * @return {Array} Array of usernames.
 */
function getUsers() {
  try {
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const loginSheet = ss.getSheetByName(LOGIN_SHEET_NAME);
    
    if (!loginSheet) {
      console.error('Login sheet not found.');
      return [];
    }
    
    const data = loginSheet.getDataRange().getValues();
    const users = [];
    
    // Start from row 2 (index 1) to ignore headers.
    for (let i = 1; i < data.length; i++) {
      if (data[i][0]) {
        users.push(data[i][0]);
      }
    }
    
    return users;
  } catch (e) {
    console.error('Error getting users:', e);
    return [];
  }
}

/**
 * Adds a new user to the Login sheet.
 * @param {string} masterPassword The master password.
 * @param {string} username The new username.
 * @param {string} password The new password.
 * @return {Object} Result object with success flag and message.
 */
function addUser(masterPassword, username, password) {
  try {
    // Verify master password
    if (!verifyMasterPassword(masterPassword)) {
      return { success: false, message: 'Invalid master password.' };
    }
    
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const loginSheet = ss.getSheetByName(LOGIN_SHEET_NAME);
    
    if (!loginSheet) {
      return { success: false, message: 'Login sheet not found.' };
    }
    
    // Check if username already exists
    const data = loginSheet.getDataRange().getValues();
    for (let i = 1; i < data.length; i++) {
      if (data[i][0] === username) {
        return { success: false, message: 'Username already exists.' };
      }
    }
    
    // Add new user
    loginSheet.appendRow([username, password]);
    
    return { success: true, message: 'User added successfully.' };
  } catch (e) {
    console.error('Error adding user:', e);
    return { success: false, message: 'Error adding user: ' + e.message };
  }
}


/**
 * Deletes a user from the Login sheet.
 * @param {string} masterPassword The master password.
 * @param {string} username The username to delete.
 * @return {Object} Result object with success flag and message.
 */
function deleteUser(masterPassword, username) {
  try {
    // Verify master password
    if (!verifyMasterPassword(masterPassword)) {
      return { success: false, message: 'Invalid master password.' };
    }
    
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const loginSheet = ss.getSheetByName(LOGIN_SHEET_NAME);
    
    if (!loginSheet) {
      return { success: false, message: 'Login sheet not found.' };
    }
    
    // Find and delete user
    const data = loginSheet.getDataRange().getValues();
    for (let i = 1; i < data.length; i++) {
      if (data[i][0] === username) {
        loginSheet.deleteRow(i + 1); // +1 because sheet rows are 1-indexed
        return { success: true, message: 'User deleted successfully.' };
      }
    }
    
    return { success: false, message: 'User not found.' };
  } catch (e) {
    console.error('Error deleting user:', e);
    return { success: false, message: 'Error deleting user: ' + e.message };
  }
}


/**
 * Resets the master password.
 * @param {string} currentPassword The current master password.
 * @param {string} newPassword The new master password.
 * @return {Object} Result object with success flag and message.
 */
function resetMasterPassword(currentPassword, newPassword) {
  return setMasterPassword(currentPassword, newPassword);
}


/**
 * Gets the credentials from the Credentials sheet.
 * @return {Array} Array of credential objects.
 */
function getCredentials() {
  try {
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const credSheet = ss.getSheetByName(CREDENTIALS_SHEET_NAME);
    
    if (!credSheet) {
      console.error('Credentials sheet not found.');
      return [];
    }
    
    const data = credSheet.getDataRange().getValues();
    const credentials = [];
    let currentSection = '';
    let id = 0;
    
    // Skip row 1 as requested
    for (let i = 1; i < data.length; i++) {
      const row = data[i];
      
      // Check if this is a section header (bold text in column A)
      if (row[0] && !row[1] && !row[2]) {
        currentSection = row[0];
        continue;
      }
      
      // Skip empty rows
      if (!row[0]) {
        continue;
      }
      
      // Check if this row has a red dot in column D
      const isEditable = (row[3] === '•');
      
      // Check if this is a non-editable highlighted row (rows 14-16)
      const isHighlighted = (i >= 13 && i <= 15); // Rows 14-16 (0-indexed would be 13-15)
      
      credentials.push({
        id: id++,
        section: currentSection,
        label: row[0],
        value: row[1] || '',
        fileName: row[2] || '',
        editable: isEditable && !isHighlighted, // Not editable if highlighted
        highlighted: isHighlighted
      });
    }
    
    return credentials;
  } catch (e) {
    console.error('Error getting credentials:', e);
    return [];
  }
}

/**
 * Verifies if the provided master password is correct.
 * @param {string} masterPassword The master password to verify.
 * @return {boolean} True if the password is correct, false otherwise.
 */
function verifyMasterPassword(masterPassword) {
  try {
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const loginSheet = ss.getSheetByName(LOGIN_SHEET_NAME);
    
    if (!loginSheet) {
      console.error('Login sheet not found.');
      return false;
    }
    
    // Check both F1 and F2 for master password
    const masterPasswordF1 = loginSheet.getRange('F1').getValue();
    const masterPasswordF2 = loginSheet.getRange('F2').getValue();
    
    console.log(`Master password from F1: "${masterPasswordF1}"`);
    console.log(`Master password from F2: "${masterPasswordF2}"`);
    console.log(`Provided password: "${masterPassword}"`);
    
    // Compare the passwords - check both locations
    return (masterPassword === masterPasswordF1) || (masterPassword === masterPasswordF2);
  } catch (e) {
    console.error('Error verifying master password:', e);
    return false;
  }
}


/**
 * Gets credentials after verifying master password.
 * @param {string} masterPassword The master password.
 * @return {Object} Object containing success flag and credentials data.
 */
function getCredentialsWithAuth(masterPassword) {
  try {
    // Verify the master password
    if (!verifyMasterPassword(masterPassword)) {
      return {
        success: false,
        message: 'Invalid master password.'
      };
    }
    
    // Get the credentials
    const credentials = getCredentials();
    
    return {
      success: true,
      credentials: credentials
    };
  } catch (e) {
    console.error('Error getting credentials with auth:', e);
    return {
      success: false,
      message: 'Error retrieving credentials: ' + e.message
    };
  }
}


/**
 * Saves updated credentials to the Credentials sheet after verifying master password.
 * @param {string} masterPassword The master password.
 * @param {Array} credentials Array of credential objects to update.
 * @return {Object} Result object with success flag and message.
 */
function saveCredentialsWithAuth(masterPassword, credentials) {
  try {
    // Verify the master password
    if (!verifyMasterPassword(masterPassword)) {
      return {
        success: false,
        message: 'Invalid master password.'
      };
    }
    
    // Save the credentials
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const credSheet = ss.getSheetByName(CREDENTIALS_SHEET_NAME);
    
    if (!credSheet) {
      return { success: false, message: 'Credentials sheet not found.' };
    }
    
    // Rest of your existing code...
    const data = credSheet.getDataRange().getValues();
    let currentSection = '';
    let id = 0;
    
    // Skip row 1 as requested
    for (let i = 1; i < data.length; i++) {
      const row = data[i];
      
      // Check if this is a section header
      if (row[0] && !row[1] && !row[2]) {
        currentSection = row[0];
        continue;
      }
      
      // Skip empty rows
      if (!row[0]) {
        continue;
      }
      
      // Check if this row has a red dot in column D and is not a highlighted row (rows 14-16)
      const isEditable = (row[3] === '•');
      const isHighlighted = (i >= 13 && i <= 15); // Rows 14-16 (0-indexed would be 13-15)
      
      if (isEditable && !isHighlighted) {
        // Find the matching credential
        const credential = credentials.find(c => Number(c.id) === id);
        if (credential) {
          // Update the value in the sheet
          credSheet.getRange(i + 1, 2).setValue(credential.value);
        }
      }
      
      id++;
    }
    
    return { success: true, message: 'Credentials updated successfully.' };
  } catch (e) {
    console.error('Error saving credentials with auth:', e);
    return { success: false, message: 'Error saving credentials: ' + e.message };
  }
}


/**
 * Looks up a UPC in the Master List sheet.
 * @param {string} upc The UPC to look up.
 * @return {Object} Result object with product data.
 */
function lookupUpcForWebApp(upc) {
  try {
    console.log(`Looking up UPC: ${upc}`);
    
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const sheet = ss.getSheetByName(MASTER_LIST_SHEET_NAME);
    
    if (!sheet) {
      return { 
        success: false, 
        message: 'Master List sheet not found.' 
      };
    }
    
    const data = sheet.getDataRange().getValues();
    const headers = data[0];
    
    // Find the UPC column index
    const upcIndex = headers.indexOf('UPC');
    if (upcIndex === -1) {
      return { 
        success: false, 
        message: 'UPC column not found in Master List.' 
      };
    }
    
    // Find the ExpDate column index
    const expDateIndex = headers.indexOf('ExpDate');
    
    // Find the Category column index
    const categoryIndex = headers.indexOf('Category');
    
    // Search for the UPC
    for (let i = 1; i < data.length; i++) {
      if (String(data[i][upcIndex]).trim() === String(upc).trim()) {
        console.log(`UPC ${upc} found at row ${i+1}`);
        
        // Create an object with all the product data
        const productData = {};
        
        // Process each column
        for (let j = 0; j < headers.length; j++) {
          const header = headers[j];
          if (header) {
            const value = data[i][j];
            
            // Special handling for ExpDate
            if (j === expDateIndex && value instanceof Date) {
              // Format date as YYYY-MM-DD for HTML date input
              const year = value.getFullYear();
              const month = String(value.getMonth() + 1).padStart(2, '0');
              const day = String(value.getDate()).padStart(2, '0');
              productData['expDate'] = `${year}-${month}-${day}`;
              console.log(`Formatted expDate: ${productData['expDate']}`);
            } 
            // Special handling for Category
            else if (j === categoryIndex) {
              productData['category'] = value || '';
            }
            // Standard handling for other fields
            else {
              productData[header.toLowerCase()] = value;
            }
          }
        }
        
        console.log("Product data:", productData);
        
        return {
          success: true,
          found: true,
          message: `Product found: ${productData.name || upc}`,
          data: productData
        };
      }
    }
    
    console.log(`UPC ${upc} not found`);
    return {
      success: true,
      found: false,
      message: `UPC ${upc} not found in Master List.`
    };
  } catch (e) {
    console.error('Error in lookupUpcForWebApp:', e);
    return { 
      success: false, 
      message: 'Error looking up UPC: ' + e.message 
    };
  }
}


/**
 * Gets the current inventory status.
 * @return {Object} Inventory status data.
 */
function getInventoryStatus() {
  try {
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const sheet = ss.getSheetByName(MASTER_LIST_SHEET_NAME);
    
    if (!sheet) {
      return { 
        success: false, 
        message: 'Master List sheet not found.' 
      };
    }
    
    const data = sheet.getDataRange().getValues();
    const headers = data[0];
    
    // Find the required column indexes
    const upcIndex = headers.indexOf('UPC');
    const brandIndex = headers.indexOf('Brand');
    const nameIndex = headers.indexOf('Name');
    const sizeIndex = headers.indexOf('Size');
    const priceIndex = headers.indexOf('Price');
    const qtyIndex = headers.indexOf('QTY');
    
    if (upcIndex === -1 || brandIndex === -1 || nameIndex === -1 || 
        sizeIndex === -1 || priceIndex === -1 || qtyIndex === -1) {
      return { 
        success: false, 
        message: 'Required columns not found in Master List.' 
      };
    }
    
    // Process inventory data
    const items = [];
    let totalQuantity = 0;
    let totalValue = 0;
    
    for (let i = 1; i < data.length; i++) {
      const row = data[i];
      const qty = Number(row[qtyIndex]) || 0;
      
      // Only include items with positive quantity
      if (qty > 0) {
        const price = Number(row[priceIndex]) || 0;
        const value = price * qty;
        
        items.push({
          upc: row[upcIndex],
          brand: row[brandIndex],
          name: row[nameIndex],
          size: row[sizeIndex],
          price: price,
          qty: qty,
          value: value
        });
        
        totalQuantity += qty;
        totalValue += value;
      }
    }
    
    // Sort items by value (highest to lowest)
    items.sort((a, b) => b.value - a.value);
    
    return {
      success: true,
      items: items,
      totalQuantity: totalQuantity,
      totalValue: totalValue
    };
  } catch (e) {
    console.error('Error in getInventoryStatus:', e);
    return { 
      success: false, 
      message: 'Error getting inventory status: ' + e.message 
    };
  }
}

/**
 * Requests product information from online sources.
 * @param {string} upc The UPC to look up.
 * @return {Object} Result object with product data.
 */
function requestProductInfo(upc) {
  return requestInfoForWebApp(upc);
}

/**
 * Saves product data to the Master List sheet.
 * @param {Object} product The product data to save.
 * @return {Object} Result object with success flag and message.
 */
function saveProduct(product) {
  return saveProductFromWebApp(product);
}

/**
 * Gets discount data from the Discounts sheet.
 * @return {Object} Result object with discount data.
 */
function getDiscounts() {
  try {
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const discountSheet = ss.getSheetByName('Discounts');
    
    if (!discountSheet) {
      return { 
        success: false, 
        message: 'Discounts sheet not found. Please create a sheet named "Discounts".' 
      };
    }
    
    // Get all discount data
    const data = discountSheet.getDataRange().getValues();
    const headers = data[0];
    
    // Process discounts
    const discounts = [];
    const categories = new Set();
    
    // Get categories from Master List for dropdown
    const masterSheet = ss.getSheetByName(MASTER_LIST_SHEET_NAME);
    if (masterSheet) {
      const masterData = masterSheet.getDataRange().getValues();
      const categoryIndex = masterData[0].indexOf('Category');
      
      if (categoryIndex !== -1) {
        for (let i = 1; i < masterData.length; i++) {
          if (masterData[i][categoryIndex]) {
            categories.add(masterData[i][categoryIndex]);
          }
        }
      }
    }
    
    // Skip header row
    for (let i = 1; i < data.length; i++) {
      const row = data[i];
      
      // Skip empty rows
      if (!row[0]) continue;
      
      discounts.push({
        code: row[0],
        type: row[1] || 'Coupon',
        once: row[2] === true,
        expiration: row[3] ? Utilities.formatDate(new Date(row[3]), Session.getScriptTimeZone(), 'MM/dd/yyyy') : '',
        dollar: row[4] || '',
        percent: row[5] || '',
        total: row[6] === true,
        category: row[7] || '',
        item1: row[8] || '',
        item2: row[9] || '',
        item3: row[10] || '',
        item4: row[11] || '',
        item5: row[12] || ''
      });
    }
    
    return {
      success: true,
      discounts: discounts,
      categories: Array.from(categories).sort()
    };
  } catch (e) {
    console.error('Error getting discounts:', e);
    return { 
      success: false, 
      message: 'Error getting discounts: ' + e.message 
    };
  }
}

/**
 * Saves a discount to the Discounts sheet.
 * @param {Object} discountData The discount data to save.
 * @return {Object} Result object with success flag and message.
 */
function saveDiscount(discountData) {
  try {
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    let discountSheet = ss.getSheetByName('Discounts');
    
    // Create the sheet if it doesn't exist
    if (!discountSheet) {
      discountSheet = ss.insertSheet('Discounts');
      // Add headers
      discountSheet.appendRow([
        'Code', 'Type', 'One-time Use', 'Expiration Date', 'Dollar Amount', 
        'Percent', 'Apply to Total', 'Category', 'Item 1', 'Item 2', 
        'Item 3', 'Item 4', 'Item 5'
      ]);
    }
    
    // Check if this is an update or new discount
    const data = discountSheet.getDataRange().getValues();
    let rowIndex = -1;
    
    if (discountData.rowIndex) {
      // This is an update
      rowIndex = parseInt(discountData.rowIndex);
    } else {
      // Check if code already exists
      for (let i = 1; i < data.length; i++) {
        if (data[i][0] === discountData.code) {
          rowIndex = i + 1; // +1 because sheet rows are 1-indexed
          break;
        }
      }
    }
    
    // Parse expiration date
    let expirationDate = null;
    if (discountData.expiration) {
      expirationDate = new Date(discountData.expiration);
    }
    
    // Prepare row data
    const rowData = [
      discountData.code,
      discountData.type,
      discountData.once === true,
      expirationDate,
      discountData.dollar ? parseFloat(discountData.dollar) : '',
      discountData.percent ? parseFloat(discountData.percent) : '',
      discountData.total === true,
      discountData.category,
      discountData.item1,
      discountData.item2,
      discountData.item3,
      discountData.item4,
      discountData.item5
    ];
    
    if (rowIndex > 0) {
      // Update existing row
      discountSheet.getRange(rowIndex, 1, 1, rowData.length).setValues([rowData]);
      return { 
        success: true, 
        message: 'Discount updated successfully.' 
      };
    } else {
      // Add new row
      discountSheet.appendRow(rowData);
      return { 
        success: true, 
        message: 'Discount added successfully.' 
      };
    }
  } catch (e) {
    console.error('Error saving discount:', e);
    return { 
      success: false, 
      message: 'Error saving discount: ' + e.message 
    };
  }
}

/**
 * Deletes a discount from the Discounts sheet.
 * @param {string} code The discount code to delete.
 * @return {Object} Result object with success flag and message.
 */
function deleteDiscount(code) {
  try {
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const discountSheet = ss.getSheetByName('Discounts');
    
    if (!discountSheet) {
      return { 
        success: false, 
        message: 'Discounts sheet not found.' 
      };
    }
    
    // Find the discount
    const data = discountSheet.getDataRange().getValues();
    for (let i = 1; i < data.length; i++) {
      if (data[i][0] === code) {
        discountSheet.deleteRow(i + 1); // +1 because sheet rows are 1-indexed
        return { 
          success: true, 
          message: 'Discount deleted successfully.' 
        };
      }
    }
    
    return { 
      success: false, 
      message: 'Discount not found.' 
    };
  } catch (e) {
    console.error('Error deleting discount:', e);
    return { 
      success: false, 
      message: 'Error deleting discount: ' + e.message 
    };
  }
}


/**
 * Exports inventory status to HTML and converts to PDF
 * @return {Blob} PDF blob
 */
function exportInventoryStatusToHTMLPDF() {
  try {
    // Get inventory data
    const inventoryData = getInventoryData();
    
    // Method 1: Try using Google Docs (most reliable)
    const doc = DocumentApp.create('Temp_Inventory_Report_' + new Date().getTime());
    const body = doc.getBody();
    body.clear();
    
    // Add title
    const title = body.appendParagraph('INVENTORY STATUS REPORT');
    title.setHeading(DocumentApp.ParagraphHeading.TITLE);
    title.setAlignment(DocumentApp.HorizontalAlignment.CENTER);
    
    // Add date
    const dateInfo = body.appendParagraph(`Generated on: ${new Date().toLocaleString()}`);
    dateInfo.setAlignment(DocumentApp.HorizontalAlignment.CENTER);
    body.appendParagraph('');
    
    // Create table data
    const tableData = [['UPC', 'Brand', 'Name', 'Size', 'Price', 'Quantity', 'Value']];
    
    inventoryData.items.forEach(item => {
      tableData.push([
        item.upc,
        item.brand,
        item.name,
        item.size,
        '$' + item.price.toFixed(2),
        item.quantity.toString(),
        '$' + item.value.toFixed(2)
      ]);
    });
    
    tableData.push(['', '', '', '', 'TOTALS:', inventoryData.totalQuantity.toString(), '$' + inventoryData.totalValue.toFixed(2)]);
    
    const table = body.appendTable(tableData);
    
    // Style the table
    table.getRow(0).setBackgroundColor('#f2f2f2');
    const lastRow = table.getRow(table.getNumRows() - 1);
    lastRow.setBackgroundColor('#f2f2f2');
    lastRow.setBold(true);
    
    doc.saveAndClose();
    
    // Convert to PDF and save to Drive
    const docFile = DriveApp.getFileById(doc.getId());
    const pdfBlob = docFile.getAs('application/pdf');
    pdfBlob.setName('Inventory_Status_Report.pdf');
    
    // Clean up the temporary Google Doc
    DriveApp.getFileById(doc.getId()).setTrashed(true);
    
    // Return the PDF blob directly
    return pdfBlob;
    
  } catch (error) {
    console.error('Error in exportInventoryStatusToHTMLPDF:', error);
    throw new Error('Failed to generate inventory report: ' + error.message);
  }
}

/**
 * Initializes the master password if it's not already set.
 */
function initializeMasterPassword() {
  try {
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const loginSheet = ss.getSheetByName(LOGIN_SHEET_NAME);
    
    if (!loginSheet) {
      console.error('Login sheet not found.');
      return;
    }
    
    // Check if master password is already set
    const masterPasswordF1 = loginSheet.getRange('F1').getValue();
    const masterPasswordF2 = loginSheet.getRange('F2').getValue();
    
    if (!masterPasswordF1 && !masterPasswordF2) {
      // Set the default master password
      loginSheet.getRange('F1').setValue(MASTER_PASSWORD);
      console.log('Master password initialized.');
    }
  } catch (e) {
    console.error('Error initializing master password:', e);
  }
}


/**
 * Gets inventory data from the Master List sheet
 * @return {Object} Object containing items array, totalQuantity, and totalValue
 */
function getInventoryData() {
  try {
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const masterSheet = ss.getSheetByName(MASTER_LIST_SHEET_NAME);
    
    if (!masterSheet) {
      throw new Error(`Sheet '${MASTER_LIST_SHEET_NAME}' not found`);
    }
    
    const data = masterSheet.getDataRange().getValues();
    
    if (data.length <= 1) {
      return {
        items: [],
        totalQuantity: 0,
        totalValue: 0
      };
    }
    
    const items = [];
    let totalQuantity = 0;
    let totalValue = 0;
    
    // Skip header row (index 0)
    for (let i = 1; i < data.length; i++) {
      const row = data[i];
      
      // Skip empty rows
      if (!row[0] && !row[1] && !row[2]) continue;
      
      // Based on your actual column structure:
      // A=UPC, B=Brand, C=Name, D=Details, E=Size, F=Calories, G=Sugar, H=Sodium, 
      // I=Price, J=Taxable, K=QTY, L=Image, M=Cost, N=Purchase Unit Qty, O=Indv Cost, P=Profit, Q=ExpDate, R=Category
      
      const upc = row[0] || '';           // Column A - UPC
      const brand = row[1] || '';         // Column B - Brand  
      const name = row[2] || '';          // Column C - Name
      const size = row[4] || '';          // Column E - Size
      const price = parseFloat(row[8]) || 0;  // Column I - Price
      const quantity = parseInt(row[10]) || 0; // Column K - QTY
      const value = price * quantity;
      
      items.push({
        upc: upc.toString(),
        brand: brand.toString(),
        name: name.toString(),
        size: size.toString(),
        price: price,
        quantity: quantity,
        value: value
      });
      
      totalQuantity += quantity;
      totalValue += value;
    }
    
    return {
      items: items,
      totalQuantity: totalQuantity,
      totalValue: totalValue
    };
    
  } catch (error) {
    console.error('Error in getInventoryData:', error);
    throw new Error('Failed to retrieve inventory data: ' + error.message);
  }
}
/**
 * Gets expiration data from the Master List sheet
 * @return {Object} Object containing items with expiration dates and summary counts
 */
function getExpirationData() {
  try {
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const masterSheet = ss.getSheetByName(MASTER_LIST_SHEET_NAME);
    
    if (!masterSheet) {
      throw new Error(`Sheet '${MASTER_LIST_SHEET_NAME}' not found`);
    }
    
    const data = masterSheet.getDataRange().getValues();
    const headers = data[0];
    
    // Find column indices
    const upcIndex = headers.indexOf('UPC');
    const brandIndex = headers.indexOf('Brand');
    const nameIndex = headers.indexOf('Name');
    const qtyIndex = headers.indexOf('QTY');
    const expDateIndex = headers.indexOf('ExpDate');
    const categoryIndex = headers.indexOf('Category');
    
    if (upcIndex === -1 || brandIndex === -1 || nameIndex === -1 || 
        qtyIndex === -1 || expDateIndex === -1) {
      throw new Error('Required columns not found in Master List');
    }
    
    const today = new Date();
    today.setHours(0, 0, 0, 0); // Set to beginning of day
    
    const items = [];
    const categories = new Set();
    let expiredCount = 0;
    let expiring7Count = 0;
    let expiring30Count = 0;
    let expiring90Count = 0;
    
    // Skip header row (index 0)
    for (let i = 1; i < data.length; i++) {
      const row = data[i];
      
      // Skip empty rows or rows without expiration date
      if (!row[upcIndex] || !row[expDateIndex]) continue;
      
      // Skip items with zero quantity
      const quantity = parseInt(row[qtyIndex]) || 0;
      if (quantity <= 0) continue;
      
      // Process expiration date
      let expDate = row[expDateIndex];
      let formattedExpDate = '';
      let daysLeft = 0;
      
      if (expDate instanceof Date && !isNaN(expDate)) {
        // Calculate days until expiration
        expDate.setHours(0, 0, 0, 0); // Set to beginning of day
        daysLeft = Math.floor((expDate - today) / (1000 * 60 * 60 * 24));
        
        // Format date as MM/DD/YYYY
        formattedExpDate = (expDate.getMonth() + 1) + '/' + expDate.getDate() + '/' + expDate.getFullYear();
      } else if (typeof expDate === 'string' && expDate.trim() !== '') {
        // Try to parse string date
        try {
          const parsedDate = new Date(expDate);
          if (!isNaN(parsedDate)) {
            parsedDate.setHours(0, 0, 0, 0);
            daysLeft = Math.floor((parsedDate - today) / (1000 * 60 * 60 * 24));
            formattedExpDate = expDate;
          }
        } catch (e) {
          console.error('Error parsing date:', e);
          formattedExpDate = expDate;
        }
      }
      
      // Get category
      const category = row[categoryIndex] || 'Uncategorized';
      categories.add(category);
      
      // Add to appropriate count
      if (daysLeft <= 0) {
        expiredCount++;
      } else if (daysLeft <= 7) {
        expiring7Count++;
      } else if (daysLeft <= 30) {
        expiring30Count++;
      } else if (daysLeft <= 90) {
        expiring90Count++;
      }
      
      // Only add items with expiration dates
      if (formattedExpDate) {
        items.push({
          upc: row[upcIndex].toString(),
          brand: row[brandIndex] || '',
          name: row[nameIndex] || '',
          category: category,
          quantity: quantity,
          expDate: formattedExpDate,
          daysLeft: daysLeft
        });
      }
    }
    
    // Sort items by days left (ascending)
    items.sort((a, b) => a.daysLeft - b.daysLeft);
    
    return {
      success: true,
      items: items,
      categories: Array.from(categories).sort(),
      expiredCount: expiredCount,
      expiring7Count: expiring7Count,
      expiring30Count: expiring30Count,
      expiring90Count: expiring90Count
    };
    
  } catch (error) {
    console.error('Error in getExpirationData:', error);
    return { 
      success: false, 
      message: 'Error getting expiration data: ' + error.message 
    };
  }
}

/**
 * Records inventory loss in the Loss Tracking sheet and updates Master List
 * @param {Array} lossItems Array of objects with UPC and quantity
 * @param {string} reason Reason for the loss
 * @param {string} notes Additional notes
 * @return {Object} Result object with success flag and message
 */
function recordInventoryLoss(lossItems, reason, notes) {
  try {
    if (!lossItems || lossItems.length === 0) {
      return {
        success: false,
        message: 'No items provided for loss recording'
      };
    }
    
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    
    // Get Loss Tracking sheet
    let lossSheet = ss.getSheetByName('Loss Tracking');
    if (!lossSheet) {
      return {
        success: false,
        message: 'Loss Tracking sheet not found'
      };
    }
    
    // Check if headers exist, if not add them
    const lossHeaders = lossSheet.getRange(1, 1, 1, 8).getValues()[0];
    if (!lossHeaders[0]) {
      lossSheet.getRange(1, 1, 1, 8).setValues([
        ['Date', 'UPC', 'Product Name/Brand', 'Quantity Lost', 'Reason', 'Notes', 'Notes', 'Recorded By']
      ]);
      lossSheet.getRange(1, 1, 1, 8).setFontWeight('bold');
    }
    
    // Get Master List sheet for updating quantities
    const masterSheet = ss.getSheetByName(MASTER_LIST_SHEET_NAME);
    if (!masterSheet) {
      throw new Error(`Sheet '${MASTER_LIST_SHEET_NAME}' not found`);
    }
    
    const masterData = masterSheet.getDataRange().getValues();
    const headers = masterData[0];
    
    // Find column indices in Master List
    const upcIndex = headers.indexOf('UPC');
    const nameIndex = headers.indexOf('Name');
    const brandIndex = headers.indexOf('Brand');
    const qtyIndex = headers.indexOf('QTY');
    
    if (upcIndex === -1 || nameIndex === -1 || brandIndex === -1 || qtyIndex === -1) {
      throw new Error('Required columns not found in Master List');
    }
    
    const today = new Date();
    const username = Session.getActiveUser().getEmail() || 'System';
    
    // Process each loss item
    for (const lossItem of lossItems) {
      const upc = lossItem.upc;
      const lossQty = lossItem.quantity;
      
      if (!upc || lossQty <= 0) continue;
      
      // Find the item in Master List
      let rowIndex = -1;
      let productName = '';
      let brand = '';
      
      for (let i = 1; i < masterData.length; i++) {
        if (String(masterData[i][upcIndex]) === String(upc)) {
          rowIndex = i + 1; // +1 because sheet rows are 1-indexed
          productName = masterData[i][nameIndex] || '';
          brand = masterData[i][brandIndex] || '';
          break;
        }
      }
      
      if (rowIndex === -1) {
        console.warn(`Item with UPC ${upc} not found in Master List`);
        continue;
      }
      
      // Update quantity in Master List
      const currentQty = parseInt(masterData[rowIndex - 1][qtyIndex]) || 0;
      const newQty = Math.max(0, currentQty - lossQty);
      masterSheet.getRange(rowIndex, qtyIndex + 1).setValue(newQty);
      
      // Record loss in Loss Tracking sheet
      // Format matches your existing sheet: Date, UPC, Product Name/Brand, Quantity Lost, Reason, Notes, Notes, Recorded By
      lossSheet.appendRow([
        today,
        upc,
        `${productName} / ${brand}`, // Combined Product Name/Brand
        lossQty,
        reason,
        notes,
        '', // Extra Notes column
        username
      ]);
    }
    
    return {
      success: true,
      message: 'Inventory loss recorded successfully!'
    };
    
  } catch (error) {
    console.error('Error in recordInventoryLoss:', error);
    return {
      success: false,
      message: 'Error recording inventory loss: ' + error.message
    };
  }
}



/**
 * Gets inventory turnover data
 * @param {string} period Time period in days
 * @param {string} category Category filter
 * @return {Object} Turnover data
 */
function getInventoryTurnoverData(period, category) {
  // The updated function from above that works with your transaction structure
  // [Insert the updated function here]
}

/**
 * Exports inventory turnover report to PDF
 * @param {string} period Time period in days
 * @param {string} category Category filter
 * @return {string} URL to the generated PDF
 */
function exportTurnoverReportToHTMLPDF(period, category) {
  try {
    // Get turnover data
    const turnoverData = getInventoryTurnoverData(period, category);
    
    if (!turnoverData.success) {
      throw new Error(turnoverData.message);
    }
    
    // Create a Google Doc for the report
    const doc = DocumentApp.create('Inventory_Turnover_Report_' + new Date().getTime());
    const body = doc.getBody();
    body.clear();
    
    // Add title
    const title = body.appendParagraph('INVENTORY TURNOVER REPORT');
    title.setHeading(DocumentApp.ParagraphHeading.TITLE);
    title.setAlignment(DocumentApp.HorizontalAlignment.CENTER);
    
    // Add period and date
    const periodText = period === '30' ? '30 Days' : 
                      period === '90' ? '90 Days' : 
                      period === '180' ? '180 Days' : '365 Days';
    const categoryText = category === 'all' ? 'All Categories' : `Category: ${category}`;
    const dateInfo = body.appendParagraph(`Period: Last ${periodText} - ${categoryText} - Generated on: ${new Date().toLocaleString()}`);
    dateInfo.setAlignment(DocumentApp.HorizontalAlignment.CENTER);
    body.appendParagraph('');
    
    // Add summary
    const summaryPara = body.appendParagraph('Summary:');
    summaryPara.setHeading(DocumentApp.ParagraphHeading.HEADING2);
    
    body.appendListItem(`Overall Turnover Ratio: ${turnoverData.overallTurnover.toFixed(2)}`).setGlyphType(DocumentApp.GlyphType.BULLET);
    body.appendListItem(`Average Days in Inventory: ${Math.round(turnoverData.avgDaysInInventory)}`).setGlyphType(DocumentApp.GlyphType.BULLET);
    body.appendListItem(`Slow-Moving Items: ${turnoverData.slowItemsCount}`).setGlyphType(DocumentApp.GlyphType.BULLET);
    body.appendListItem(`Fast-Moving Items: ${turnoverData.fastItemsCount}`).setGlyphType(DocumentApp.GlyphType.BULLET);
    
    body.appendParagraph('');
    
    // Add category turnover section
    if (turnoverData.categoryTurnover && turnoverData.categoryTurnover.length > 0) {
      const catPara = body.appendParagraph('Turnover by Category:');
      catPara.setHeading(DocumentApp.ParagraphHeading.HEADING2);
      
      const catTableData = [['Category', 'Turnover Ratio']];
      turnoverData.categoryTurnover.forEach(cat => {
        catTableData.push([cat.category, cat.turnoverRatio.toFixed(2)]);
      });
      
      const catTable = body.appendTable(catTableData);
      catTable.getRow(0).setBackgroundColor('#f2f2f2');
    }
    
    body.appendParagraph('');
    
    // Add items table
    if (turnoverData.items && turnoverData.items.length > 0) {
      const itemsPara = body.appendParagraph('Detailed Turnover Analysis:');
      itemsPara.setHeading(DocumentApp.ParagraphHeading.HEADING2);
      
      // Create table data
      const tableData = [['UPC', 'Brand', 'Name', 'Category', 'Beginning', 'Ending', 'Units Sold', 'Turnover', 'Days', 'Status']];
      
      turnoverData.items.forEach(item => {
        // Format the status text
        let statusText = '';
        if (item.turnoverRatio < 1) {
          statusText = 'VERY SLOW';
        } else if (item.turnoverRatio < 2) {
          statusText = 'SLOW';
        } else if (item.turnoverRatio > 6) {
          statusText = 'FAST';
        } else {
          statusText = 'OPTIMAL';
        }
        
        tableData.push([
          item.upc,
          item.brand,
          item.name,
          item.category,
          item.beginningInventory.toString(),
          item.endingInventory.toString(),
          item.unitsSold.toString(),
          item.turnoverRatio.toFixed(2),
          Math.round(item.daysInInventory).toString(),
          statusText
        ]);
      });
      
      const table = body.appendTable(tableData);
      table.getRow(0).setBackgroundColor('#f2f2f2');
      
      // Color code rows based on turnover status
      for (let i = 1; i < table.getNumRows(); i++) {
        const turnoverRatio = turnoverData.items[i-1].turnoverRatio;
        
        if (turnoverRatio < 1) {
          table.getRow(i).setBackgroundColor('#ffcccc'); // Light red for very slow
        } else if (turnoverRatio < 2) {
          table.getRow(i).setBackgroundColor('#ffeecc'); // Light orange for slow
        } else if (turnoverRatio > 6) {
          table.getRow(i).setBackgroundColor('#ccccff'); // Light blue for fast
        } else {
          table.getRow(i).setBackgroundColor('#ccffcc'); // Light green for optimal
        }
      }
    } else {
      body.appendParagraph('No turnover data available for the selected period.').setItalic(true);
    }
    
    doc.saveAndClose();
    
    // Convert to PDF and save to Drive
    const docFile = DriveApp.getFileById(doc.getId());
    const pdfBlob = docFile.getAs('application/pdf');
    pdfBlob.setName('Inventory_Turnover_Report.pdf');
    
    // Save PDF to Drive
    const pdfFile = DriveApp.createFile(pdfBlob);
    
    // Clean up the temporary Google Doc
    DriveApp.getFileById(doc.getId()).setTrashed(true);
    
    // Return the PDF URL for opening in browser
    return pdfFile.getUrl();
    
  } catch (error) {
    console.error('Error in exportTurnoverReportToHTMLPDF:', error);
    throw new Error('Failed to generate turnover report: ' + error.message);
  }
}



/**
 * Exports expiration report to PDF
 * @param {string} expirationFilter Filter for expiration status
 * @param {string} categoryFilter Filter for category
 * @return {string} URL to the generated PDF
 */
function exportExpirationReportToHTMLPDF(expirationFilter, categoryFilter) {
  try {
    // Get expiration data
    const expirationData = getExpirationData();
    
    if (!expirationData.success) {
      throw new Error(expirationData.message);
    }
    
    // Filter items based on selected filters
    let filteredItems = expirationData.items;
    let filterDescription = 'All Items';
    
    // Apply expiration filter
    if (expirationFilter !== 'all') {
      switch (expirationFilter) {
        case 'expired':
          filteredItems = filteredItems.filter(item => item.daysLeft <= 0);
          filterDescription = 'Expired Items';
          break;
        case '7days':
          filteredItems = filteredItems.filter(item => item.daysLeft > 0 && item.daysLeft <= 7);
          filterDescription = 'Items Expiring in 7 Days';
          break;
        case '30days':
          filteredItems = filteredItems.filter(item => item.daysLeft > 7 && item.daysLeft <= 30);
          filterDescription = 'Items Expiring in 30 Days';
          break;
        case '90days':
          filteredItems = filteredItems.filter(item => item.daysLeft > 30 && item.daysLeft <= 90);
          filterDescription = 'Items Expiring in 90 Days';
          break;
      }
    }
    
    // Apply category filter
    if (categoryFilter !== 'all') {
      filteredItems = filteredItems.filter(item => item.category === categoryFilter);
      filterDescription += ` - Category: ${categoryFilter}`;
    }
    
    // Create a Google Doc for the report
    const doc = DocumentApp.create('Expiration_Report_' + new Date().getTime());
    const body = doc.getBody();
    body.clear();
    
    // Add title
    const title = body.appendParagraph('EXPIRATION TRACKING REPORT');
    title.setHeading(DocumentApp.ParagraphHeading.TITLE);
    title.setAlignment(DocumentApp.HorizontalAlignment.CENTER);
    
    // Add filter description and date
    const dateInfo = body.appendParagraph(`${filterDescription} - Generated on: ${new Date().toLocaleString()}`);
    dateInfo.setAlignment(DocumentApp.HorizontalAlignment.CENTER);
    body.appendParagraph('');
    
    // Add summary
    const summaryPara = body.appendParagraph('Summary:');
    summaryPara.setHeading(DocumentApp.ParagraphHeading.HEADING2);
    
    body.appendListItem(`Expired Items: ${expirationData.expiredCount}`).setGlyphType(DocumentApp.GlyphType.BULLET);
    body.appendListItem(`Expiring in 7 Days: ${expirationData.expiring7Count}`).setGlyphType(DocumentApp.GlyphType.BULLET);
    body.appendListItem(`Expiring in 30 Days: ${expirationData.expiring30Count}`).setGlyphType(DocumentApp.GlyphType.BULLET);
    body.appendListItem(`Expiring in 90 Days: ${expirationData.expiring90Count}`).setGlyphType(DocumentApp.GlyphType.BULLET);
    
    body.appendParagraph('');
    
    // Add items table
    if (filteredItems.length > 0) {
      const itemsPara = body.appendParagraph('Items:');
      itemsPara.setHeading(DocumentApp.ParagraphHeading.HEADING2);
      
     // Create table data
      const tableData = [['UPC', 'Brand', 'Name', 'Category', 'Quantity', 'Expiration Date', 'Days Left', 'Status']];
      
      filteredItems.forEach(item => {
        // Format the status text
        let statusText = '';
        if (item.daysLeft <= 0) {
          statusText = 'EXPIRED';
        } else if (item.daysLeft === 1) {
          statusText = 'EXPIRES TOMORROW';
        } else {
          statusText = `EXPIRES IN ${item.daysLeft} DAYS`;
        }
        
        tableData.push([
          item.upc,
          item.brand,
          item.name,
          item.category,
          item.quantity.toString(),
          item.expDate,
          item.daysLeft <= 0 ? 'EXPIRED' : item.daysLeft.toString(),
          statusText
        ]);
      });
      
      const table = body.appendTable(tableData);
      
      // Style the table
      table.getRow(0).setBackgroundColor('#f2f2f2');
      
      // Color code rows based on expiration status
      for (let i = 1; i < table.getNumRows(); i++) {
        const daysLeft = filteredItems[i-1].daysLeft;
        
        if (daysLeft <= 0) {
          table.getRow(i).setBackgroundColor('#ffcccc'); // Light red for expired
        } else if (daysLeft <= 7) {
          table.getRow(i).setBackgroundColor('#ffddcc'); // Light orange for 7 days
        } else if (daysLeft <= 30) {
          table.getRow(i).setBackgroundColor('#ffffcc'); // Light yellow for 30 days
        } else if (daysLeft <= 90) {
          table.getRow(i).setBackgroundColor('#f0f0f0'); // Light gray for 90 days
        }
      }
    } else {
      body.appendParagraph('No items found matching the selected filters.').setItalic(true);
    }
    
    doc.saveAndClose();
    
    // Convert to PDF and save to Drive
    const docFile = DriveApp.getFileById(doc.getId());
    const pdfBlob = docFile.getAs('application/pdf');
    pdfBlob.setName('Expiration_Report.pdf');
    
    // Save PDF to Drive
    const pdfFile = DriveApp.createFile(pdfBlob);
    
    // Clean up the temporary Google Doc
    DriveApp.getFileById(doc.getId()).setTrashed(true);
    
    // Return the PDF URL for opening in browser
    return pdfFile.getUrl();
    
  } catch (error) {
    console.error('Error in exportExpirationReportToHTMLPDF:', error);
    throw new Error('Failed to generate expiration report: ' + error.message);
  }
}



/**
 * Requests product information from online sources.
 * @param {string} upc The UPC to look up.
 * @return {Object} Result object with product data.
 */
function requestInfoForWebApp(upc) {
  try {
    console.log(`Requesting info for UPC: ${upc}`);
    
    // First check if we already have this UPC
    const existingResult = lookupUpcForWebApp(upc);
    if (existingResult.found) {
      return existingResult;
    }
    
    // For now, return a placeholder response
    // In a real implementation, you would call an external API here
    return {
      success: true,
      found: true,
      message: `Product information retrieved for ${upc}`,
      data: {
        upc: upc,
        brand: 'Unknown Brand',
        name: 'Unknown Product',
        details: 'No details available',
        size: '',
        calories: '',
        sugar: '',
        sodium: '',
        price: '',
        taxable: 'Yes',
        qty: '0',
        cost: '',
        purchaseUnitQty: '1',
        indvCost: '',
        profit: ''
      }
    };
  } catch (e) {
    console.error('Error in requestInfoForWebApp:', e);
    return { 
      success: false, 
      message: 'Error requesting product info: ' + e.message 
    };
  }
}

/**
 * Saves product data to the Master List sheet.
 * @param {Object} productData The product data to save.
 * @return {Object} Result object with success flag and message.
 */
function saveProductFromWebApp(productData) {
  try {
    console.log(`Saving product data for UPC: ${productData.upc}`);
    console.log("Product data to save:", productData);
    
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const sheet = ss.getSheetByName(MASTER_LIST_SHEET_NAME);
    
    if (!sheet) {
      return { 
        success: false, 
        message: 'Master List sheet not found.' 
      };
    }
    
    const data = sheet.getDataRange().getValues();
    const headers = data[0];
    
    // Find the UPC column index
    const upcIndex = headers.indexOf('UPC');
    if (upcIndex === -1) {
      return { 
        success: false, 
        message: 'UPC column not found in Master List.' 
      };
    }
    
    // Find the Category column index (should be column R)
    const categoryIndex = headers.indexOf('Category');
    
    // Find the ExpDate column index
    const expDateIndex = headers.indexOf('ExpDate');
    
    // Check if the UPC already exists
    let rowIndex = -1;
    for (let i = 1; i < data.length; i++) {
      if (String(data[i][upcIndex]).trim() === String(productData.upc).trim()) {
        rowIndex = i + 1; // +1 because sheet rows are 1-indexed
        break;
      }
    }
    
    // Prepare the row data
    const rowData = [];
    for (let i = 0; i < headers.length; i++) {
      const header = headers[i];
      const headerLower = header.toLowerCase();
      
      // Special handling for ExpDate column
      if (i === expDateIndex) {
        if (productData.expdate) {
          // If expdate is provided as a string, convert it to a Date object
          if (typeof productData.expdate === 'string') {
            try {
              const dateParts = productData.expdate.split('-');
              if (dateParts.length === 3) {
                const year = parseInt(dateParts[0]);
                const month = parseInt(dateParts[1]) - 1; // JS months are 0-indexed
                const day = parseInt(dateParts[2]);
                rowData.push(new Date(year, month, day));
                console.log(`Converted expDate string to Date: ${productData.expdate} -> ${new Date(year, month, day)}`);
              } else {
                rowData.push(productData.expdate);
              }
            } catch (e) {
              console.error("Error converting expdate:", e);
              rowData.push(productData.expdate);
            }
          } else {
            rowData.push(productData.expdate);
          }
        } else {
          // Keep existing value if updating
          rowData.push(rowIndex > 0 ? data[rowIndex - 1][i] : '');
        }
      }
      // Special handling for Category column
      else if (i === categoryIndex) {
        if (productData.category) {
          rowData.push(productData.category);
        } else {
          // Keep existing value if updating
          rowData.push(rowIndex > 0 ? data[rowIndex - 1][i] : '');
        }
      }
      // Normal handling for other columns
      else if (productData.hasOwnProperty(headerLower)) {
        rowData.push(productData[headerLower]);
      } else {
        // If we're updating an existing row, keep the existing value
        rowData.push(rowIndex > 0 ? data[rowIndex - 1][i] : '');
      }
    }
    
    if (rowIndex > 0) {
      // Update existing row
      sheet.getRange(rowIndex, 1, 1, rowData.length).setValues([rowData]);
      console.log(`Updated product at row ${rowIndex}`);
      return { 
        success: true, 
        message: 'Product updated successfully.',
        upc: productData.upc
      };
    } else {
      // Add new row
      sheet.appendRow(rowData);
      console.log('Added new product');
      return { 
        success: true, 
        message: 'Product added successfully.',
        upc: productData.upc
      };
    }
  } catch (e) {
    console.error('Error in saveProductFromWebApp:', e);
    return { 
      success: false, 
      message: 'Error saving product: ' + e.message 
    };
  }
}




/**
 * Generates a sales report.
 * @param {string} startDate - Start date in YYYY-MM-DD format.
 * @param {string} endDate - End date in YYYY-MM-DD format.
 * @return {object} The sales report data.
 */
function generateSalesReport(startDate, endDate) {
  try {
    console.log(`Starting report generation for date range: ${startDate} to ${endDate}`);
    
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const transSheet = ss.getSheetByName('Transactions');
    
    if (!transSheet) {
      console.error('ERROR: Transactions sheet not found');
      return { 
        success: false, 
        message: 'Transactions sheet not found. Please create a sheet named "Transactions".' 
      };
    }
    
    console.log('Transactions sheet found. Getting data...');
    
    // Get all transaction data
    const data = transSheet.getDataRange().getValues();
    const headers = data[0];
    
    console.log(`Headers found: ${headers.length} columns`);
    
    // Find column indexes by exact header names
    const dateColIndex = headers.indexOf('Date');
    const idColIndex = headers.indexOf('Transaction ID');
    const timeColIndex = headers.indexOf('Time');
    const itemsColIndex = headers.indexOf('Items');
    const paymentColIndex = headers.indexOf('Payment Method');
    const subtotalColIndex = headers.indexOf('Subtotal');
    const taxColIndex = headers.indexOf('Tax');
    const totalColIndex = headers.indexOf('Total');
    
    console.log(`Column indexes - Date: ${dateColIndex}, ID: ${idColIndex}, Subtotal: ${subtotalColIndex}, Tax: ${taxColIndex}, Total: ${totalColIndex}`);
    
    if (dateColIndex === -1) {
      console.error('Date column not found. Headers in sheet:', headers);
      return { 
        success: false, 
        message: 'Date column not found in Transactions sheet. Please check the header row.' 
      };
    }
    
    // Convert string dates to Date objects
    console.log(`Converting dates: ${startDate} and ${endDate}`);
    const startDateObj = new Date(startDate);
    const endDateObj = new Date(endDate);
    endDateObj.setHours(23, 59, 59); // Include the entire end date
    
    console.log(`Date objects - Start: ${startDateObj}, End: ${endDateObj}`);
    
    // Filter transactions by date range
    const transactions = [];
    let totalTransactions = 0;
    let totalItems = 0;
    let totalSubtotal = 0;
    let totalTax = 0;
    let totalRevenue = 0;
    
    console.log(`Processing ${data.length - 1} transaction rows...`);
    
    for (let i = 1; i < data.length; i++) {
      const row = data[i];
      
      // Skip empty rows
      if (!row[dateColIndex]) {
        console.log(`Skipping empty row ${i+1}`);
        continue;
      }
      
      // Get the date directly - it's already a Date object in Google Sheets
      const transDate = row[dateColIndex];
      
      console.log(`Row ${i+1} date: ${transDate}`);
      
      // Compare only the date part (ignore time)
      const transDateOnly = new Date(transDate.getFullYear(), transDate.getMonth(), transDate.getDate());
      const startDateOnly = new Date(startDateObj.getFullYear(), startDateObj.getMonth(), startDateObj.getDate());
      const endDateOnly = new Date(endDateObj.getFullYear(), endDateObj.getMonth(), endDateObj.getDate());
      
      if (transDateOnly >= startDateOnly && transDateOnly <= endDateOnly) {
        console.log(`Row ${i+1} is within date range`);
        
        const id = row[idColIndex] || `Unknown-${i}`;
        let time = '';
        if (timeColIndex !== -1 && row[timeColIndex]) {
          // Format time as HH:MM:SS
          const timeDate = row[timeColIndex];
          if (timeDate instanceof Date) {
            time = Utilities.formatDate(timeDate, Session.getScriptTimeZone(), 'HH:mm:ss');
          } else {
            time = String(row[timeColIndex]);
          }
        }
        
        const items = Number(row[itemsColIndex]) || 0;
        const paymentMethod = row[paymentColIndex] || 'Unknown';
        const subtotal = Number(row[subtotalColIndex]) || 0;
        const tax = Number(row[taxColIndex]) || 0;
        const total = Number(row[totalColIndex]) || 0;
        
        transactions.push({
          id: id,
          date: Utilities.formatDate(transDate, Session.getScriptTimeZone(), 'MM/dd/yyyy'),
          time: time,
          items: items,
          paymentMethod: paymentMethod,
          subtotal: subtotal,
          tax: tax,
          total: total
        });
        
        totalTransactions++;
        totalItems += items;
        totalSubtotal += subtotal;
        totalTax += tax;
        totalRevenue += total;
      } else {
        console.log(`Row ${i+1} is outside date range: ${transDateOnly} not between ${startDateOnly} and ${endDateOnly}`);
      }
    }
    
    console.log(`Report generation complete. Found ${totalTransactions} transactions.`);
    
    return {
      success: true,
      totalTransactions: totalTransactions,
      totalItems: totalItems,
      totalSubtotal: totalSubtotal,
      totalTax: totalTax,
      totalRevenue: totalRevenue,
      transactions: transactions
    };
  } catch (e) {
    console.error('ERROR in generateSalesReport:', e);
    console.error('Stack trace:', e.stack);
    return { 
      success: false, 
      message: 'Error generating report: ' + e.message 
    };
  }
}

/**
 * Generates a product performance report.
 * @param {string} startDate - Start date in YYYY-MM-DD format.
 * @param {string} endDate - End date in YYYY-MM-DD format.
 * @return {object} The product performance report data.
 */
function generateProductPerformanceReport(startDate, endDate) {
  try {
    console.log(`Starting product report generation for date range: ${startDate} to ${endDate}`);
    
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const transSheet = ss.getSheetByName('Transactions');
    const masterSheet = ss.getSheetByName(MASTER_LIST_SHEET_NAME);
    
    if (!transSheet || !masterSheet) {
      console.error('Required sheets not found');
      return { 
        success: false, 
        message: 'Required sheets not found. Please check that both "Transactions" and "Master List" sheets exist.' 
      };
    }
    
    console.log('Sheets found. Getting data...');
    
    // Get all transaction data
    const transData = transSheet.getDataRange().getValues();
    const transHeaders = transData[0];
    
    // Find column indexes by exact header names
    const dateColIndex = transHeaders.indexOf('Date');
    
    if (dateColIndex === -1) {
      console.error('Date column not found');
      return { 
        success: false, 
        message: 'Date column not found in Transactions sheet. Please check the header row.' 
      };
    }
    
    // Convert string dates to Date objects
    console.log(`Converting dates: ${startDate} and ${endDate}`);
    const startDateObj = new Date(startDate);
    const endDateObj = new Date(endDate);
    endDateObj.setHours(23, 59, 59); // Include the entire end date
    
    // Process transactions within date range
    const productMap = new Map(); // Map to track products by UPC
    let totalSales = 0;
    
    console.log(`Processing ${transData.length - 1} transaction rows...`);
    
    for (let i = 1; i < transData.length; i++) {
      const row = transData[i];
      
      // Skip empty rows
      if (!row[dateColIndex]) {
        continue;
      }
      
      // Get the date directly - it's already a Date object in Google Sheets
      const transDate = row[dateColIndex];
      
            // Compare only the date part (ignore time)
      const transDateOnly = new Date(transDate.getFullYear(), transDate.getMonth(), transDate.getDate());
      const startDateOnly = new Date(startDateObj.getFullYear(), startDateObj.getMonth(), startDateObj.getDate());
      const endDateOnly = new Date(endDateObj.getFullYear(), endDateObj.getMonth(), endDateObj.getDate());
      
      if (transDateOnly >= startDateOnly && transDateOnly <= endDateOnly) {
        console.log(`Row ${i+1} is within date range`);
        
        // Process each item in the transaction
        for (let itemNum = 1; itemNum <= 15; itemNum++) {
          const upcIndex = transHeaders.indexOf(`Item ${itemNum} UPC`);
          const nameIndex = transHeaders.indexOf(`Item ${itemNum} Name`);
          const qtyIndex = transHeaders.indexOf(`Item ${itemNum} Qty`);
          const priceIndex = transHeaders.indexOf(`Item ${itemNum} Price`);
          const totalIndex = transHeaders.indexOf(`Item ${itemNum} Total`);
          
          if (upcIndex === -1 || nameIndex === -1 || qtyIndex === -1 || priceIndex === -1) {
            // If we can't find columns for this item number, we've probably reached the end of the item columns
            break;
          }
          
          const upc = row[upcIndex];
          if (!upc) continue; // Skip empty items
          
          const name = row[nameIndex] || 'Unknown';
          const qty = Number(row[qtyIndex]) || 0;
          const price = Number(row[priceIndex]) || 0;
          const total = Number(row[totalIndex]) || 0;
          
          // Get product info from Master List
          let brand = 'Unknown';
          let profit = 0;
          
          // Look up product in Master List
          const masterData = masterSheet.getDataRange().getValues();
          const masterHeaders = masterData[0];
          
          // Find column indexes in master sheet
          const masterUpcIndex = masterHeaders.indexOf('UPC');
          const masterBrandIndex = masterHeaders.indexOf('Brand');
          const masterIndvCostIndex = masterHeaders.indexOf('Indv Cost');
          
          if (masterUpcIndex !== -1) {
            for (let j = 1; j < masterData.length; j++) {
              if (String(masterData[j][masterUpcIndex]).trim() === String(upc).trim()) {
                if (masterBrandIndex !== -1) {
                  brand = masterData[j][masterBrandIndex] || 'Unknown';
                }
                
                if (masterIndvCostIndex !== -1) {
                  const indvCost = Number(masterData[j][masterIndvCostIndex]) || 0;
                  profit = (price - indvCost) * qty;
                }
                break;
              }
            }
          }
          
          // Update product map
          if (productMap.has(upc)) {
            const product = productMap.get(upc);
            product.quantity += qty;
            product.totalSales += total;
            product.profit += profit;
          } else {
            productMap.set(upc, {
              upc: upc,
              name: name,
              brand: brand,
              quantity: qty,
              price: price,
              totalSales: total,
              profit: profit
            });
          }
          
          totalSales += total;
        }
      }
    }
    
    // Convert map to array and sort by total sales (descending)
    const products = Array.from(productMap.values())
      .sort((a, b) => b.totalSales - a.totalSales);
    
    // Calculate summary metrics
    const totalProducts = products.length;
    let totalQuantity = 0;
    let totalProfit = 0;
    
    products.forEach(product => {
      totalQuantity += product.quantity;
      totalProfit += product.profit;
    });
    
    const averagePrice = totalQuantity > 0 ? totalSales / totalQuantity : 0;
    
    console.log(`Product report generation complete. Found ${totalProducts} products.`);
    
    return {
      success: true,
      totalProducts: totalProducts,
      totalQuantity: totalQuantity,
      totalSales: totalSales,
      averagePrice: averagePrice,
      totalProfit: totalProfit,
      products: products
    };
  } catch (e) {
    console.error('ERROR in generateProductPerformanceReport:', e);
    console.error('Stack trace:', e.stack);
    return { 
      success: false, 
      message: 'Error generating product report: ' + e.message 
    };
  }
}

/**
 * Exports the sales report to PDF with enhanced HTML styling.
 * @param {string} startDate - Start date in YYYY-MM-DD format.
 * @param {string} endDate - End date in YYYY-MM-DD format.
 * @return {string} URL to the generated PDF.
 */
function exportSalesReportToHTMLPDF(startDate, endDate) {
  try {
    console.log('Starting HTML-styled PDF export for sales report');
    
    // Get the report data
    const reportData = generateSalesReport(startDate, endDate);
    
    if (!reportData.success) {
      console.error('Failed to generate report data for PDF:', reportData.message);
      return null;
    }
    
    // Format dates for the filename
    const formattedStartDate = startDate.replace(/-/g, '');
    const formattedEndDate = endDate.replace(/-/g, '');
    const timestamp = new Date().getTime();
    const fileName = `SalesReport_HTML_${formattedStartDate}_to_${formattedEndDate}_${timestamp}.pdf`;
    
    // Create HTML content
    let htmlContent = `
    <!DOCTYPE html>
    <html>
    <head>
      <style>
        body {
          font-family: Arial, sans-serif;
          margin: 0;
          padding: 20px;
          color: #333;
        }
        .header {
          text-align: center;
          margin-bottom: 30px;
        }
        .logo {
          max-width: 150px;
          margin-bottom: 10px;
        }
        h1 {
          margin: 0;
          color: #000;
          font-size: 24px;
        }
        .subtitle {
          color: #666;
          font-size: 16px;
          margin-top: 5px;
        }
        .info-row {
          display: flex;
          justify-content: space-between;
          margin-bottom: 5px;
          font-size: 14px;
        }
        .info-label {
          font-weight: bold;
        }
        .summary-section {
          margin: 30px 0;
          padding: 15px;
          background-color: #f5f5f5;
          border-radius: 5px;
        }
        .summary-title {
          font-size: 18px;
          font-weight: bold;
          margin-bottom: 15px;
          border-bottom: 1px solid #ddd;
          padding-bottom: 5px;
        }
        .summary-grid {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 15px;
        }
        .summary-item {
          text-align: center;
        }
        .summary-value {
          font-size: 20px;
          font-weight: bold;
          color: #000;
          margin-bottom: 5px;
        }
        .summary-label {
          font-size: 14px;
          color: #666;
        }
        table {
          width: 100%;
          border-collapse: collapse;
          margin-top: 20px;
        }
        th, td {
          padding: 10px;
          text-align: left;
          border-bottom: 1px solid #ddd;
        }
        th {
          background-color: #f2f2f2;
          font-weight: bold;
        }
        tr:nth-child(even) {
          background-color: #f9f9f9;
        }
        .footer {
          margin-top: 30px;
          text-align: center;
          font-size: 12px;
          color: #999;
        }
      </style>
    </head>
    <body>
      <div class="header">
        <img src="https://i.imgur.com/lfcgQ0s.png" alt="VEND LAS VEGAS Logo" class="logo">
        <h1>VEND LAS VEGAS</h1>
        <div class="subtitle">Sales Report</div>
      </div>
      
      <div class="info-row">
        <div><span class="info-label">Date Range:</span> ${formatDate(new Date(startDate))} to ${formatDate(new Date(endDate))}</div>
        <div><span class="info-label">Machine ID:</span> ${getMachineID()}</div>
      </div>
      <div class="info-row">
        <div><span class="info-label">Generated:</span> ${formatDate(new Date())} ${formatTime(new Date())}</div>
      </div>
      
      <div class="summary-section">
        <div class="summary-title">SUMMARY</div>
        <div class="summary-grid">
          <div class="summary-item">
            <div class="summary-value">${reportData.totalTransactions}</div>
            <div class="summary-label">Transactions</div>
          </div>
          <div class="summary-item">
            <div class="summary-value">${reportData.totalItems}</div>
            <div class="summary-label">Items Sold</div>
          </div>
          <div class="summary-item">
            <div class="summary-value">$${reportData.totalRevenue.toFixed(2)}</div>
            <div class="summary-label">Total Revenue</div>
          </div>
        </div>
        <div class="summary-grid" style="margin-top: 15px;">
          <div class="summary-item">
            <div class="summary-value">$${reportData.totalSubtotal.toFixed(2)}</div>
            <div class="summary-label">Subtotal</div>
          </div>
          <div class="summary-item">
            <div class="summary-value">$${reportData.totalTax.toFixed(2)}</div>
            <div class="summary-label">Tax</div>
          </div>
        </div>
      </div>
      
      <div class="summary-title">TRANSACTION DETAILS</div>
      <table>
        <thead>
          <tr>
            <th>Transaction ID</th>
            <th>Date</th>
            <th>Time</th>
            <th>Items</th>
            <th>Payment</th>
            <th>Subtotal</th>
            <th>Tax</th>
            <th>Total</th>
          </tr>
        </thead>
        <tbody>
    `;
    
    // Add transaction rows
    reportData.transactions.forEach(t => {
      htmlContent += `
      <tr>
        <td>${t.id || 'N/A'}</td>
        <td>${t.date || 'N/A'}</td>
        <td>${t.time || 'N/A'}</td>
        <td>${t.items || '0'}</td>
        <td>${t.paymentMethod || 'N/A'}</td>
        <td>$${(t.subtotal || 0).toFixed(2)}</td>
        <td>$${(t.tax || 0).toFixed(2)}</td>
        <td>$${(t.total || 0).toFixed(2)}</td>
      </tr>
      `;
    });
    
    // Close the HTML
    htmlContent += `
        </tbody>
      </table>
      
      <div class="footer">
        © ${new Date().getFullYear()} VEND LAS VEGAS. All rights reserved.
      </div>
    </body>
    </html>
    `;
    
    // Create a temporary file with the HTML content
    const htmlFile = DriveApp.createFile('temp_report.html', htmlContent, 'text/html');
    
    // Convert to PDF using Google Docs
    const blob = htmlFile.getAs('application/pdf').setName(fileName);
    const pdfFile = DriveApp.createFile(blob);
    
    // Clean up the temporary HTML file
    htmlFile.setTrashed(true);
    
    // Get the PDF URL
    const pdfUrl = pdfFile.getUrl();
    
    console.log('HTML-styled PDF export completed successfully');
    return pdfUrl;
  } catch (e) {
    console.error('Error exporting sales report to HTML PDF:', e);
    console.error('Stack trace:', e.stack);
    return null;
  }
}

/**
 * Exports the product report to PDF with enhanced HTML styling.
 * @param {string} startDate - Start date in YYYY-MM-DD format.
 * @param {string} endDate - End date in YYYY-MM-DD format.
 * @return {string} URL to the generated PDF.
 */
function exportProductReportToHTMLPDF(startDate, endDate) {
  try {
    console.log('Starting HTML-styled PDF export for product report');
    
    // Get the report data
    const reportData = generateProductPerformanceReport(startDate, endDate);
    
    if (!reportData.success) {
      console.error('Failed to generate product report data for PDF:', reportData.message);
      return null;
    }
    
    // Format dates for the filename
    const formattedStartDate = startDate.replace(/-/g, '');
    const formattedEndDate = endDate.replace(/-/g, '');
    const timestamp = new Date().getTime();
    const fileName = `ProductReport_HTML_${formattedStartDate}_to_${formattedEndDate}_${timestamp}.pdf`;
    
    // Create HTML content
    let htmlContent = `
    <!DOCTYPE html>
    <html>
    <head>
      <style>
        body {
          font-family: Arial, sans-serif;
          margin: 0;
          padding: 20px;
          color: #333;
        }
        .header {
          text-align: center;
          margin-bottom: 30px;
        }
        .logo {
          max-width: 150px;
          margin-bottom: 10px;
        }
        h1 {
          margin: 0;
          color: #000;
          font-size: 24px;
        }
        .subtitle {
          color: #666;
          font-size: 16px;
          margin-top: 5px;
        }
        .info-row {
          display: flex;
          justify-content: space-between;
          margin-bottom: 5px;
          font-size: 14px;
        }
        .info-label {
          font-weight: bold;
        }
        .summary-section {
          margin: 30px 0;
          padding: 15px;
          background-color: #f5f5f5;
          border-radius: 5px;
        }
        .summary-title {
          font-size: 18px;
          font-weight: bold;
          margin-bottom: 15px;
          border-bottom: 1px solid #ddd;
          padding-bottom: 5px;
        }
        .summary-grid {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 15px;
        }
        .summary-item {
          text-align: center;
        }
        .summary-value {
          font-size: 20px;
          font-weight: bold;
          color: #000;
          margin-bottom: 5px;
        }
        .summary-label {
          font-size: 14px;
          color: #666;
        }
        table {
          width: 100%;
          border-collapse: collapse;
          margin-top: 20px;
        }
        th, td {
          padding: 10px;
          text-align: left;
          border-bottom: 1px solid #ddd;
        }
        th {
          background-color: #f2f2f2;
          font-weight: bold;
        }
        tr:nth-child(even) {
          background-color: #f9f9f9;
        }
        .footer {
          margin-top: 30px;
          text-align: center;
          font-size: 12px;
          color: #999;
        }
      </style>
    </head>
    <body>
      <div class="header">
        <img src="https://i.imgur.com/lfcgQ0s.png" alt="VEND LAS VEGAS Logo" class="logo">
        <h1>VEND LAS VEGAS</h1>
        <div class="subtitle">Product Performance Report</div>
      </div>
      
      <div class="info-row">
        <div><span class="info-label">Date Range:</span> ${formatDate(new Date(startDate))} to ${formatDate(new Date(endDate))}</div>
        <div><span class="info-label">Machine ID:</span> ${getMachineID()}</div>
      </div>
      <div class="info-row">
        <div><span class="info-label">Generated:</span> ${formatDate(new Date())} ${formatTime(new Date())}</div>
      </div>
      
      <div class="summary-section">
        <div class="summary-title">SUMMARY</div>
        <div class="summary-grid">
          <div class="summary-item">
            <div class="summary-value">${reportData.totalProducts}</div>
            <div class="summary-label">Products Sold</div>
          </div>
          <div class="summary-item">
            <div class="summary-value">${reportData.totalQuantity}</div>
            <div class="summary-label">Total Quantity</div>
          </div>
          <div class="summary-item">
            <div class="summary-value">$${reportData.totalSales.toFixed(2)}</div>
            <div class="summary-label">Total Sales</div>
          </div>
        </div>
        <div class="summary-grid" style="margin-top: 15px;">
          <div class="summary-item">
            <div class="summary-value">$${reportData.averagePrice.toFixed(2)}</div>
            <div class="summary-label">Average Price</div>
          </div>
          <div class="summary-item">
            <div class="summary-value">$${reportData.totalProfit.toFixed(2)}</div>
            <div class="summary-label">Total Profit</div>
          </div>
        </div>
      </div>
      
      <div class="summary-title">TOP SELLING PRODUCTS</div>
      <table>
        <thead>
          <tr>
            <th>UPC</th>
            <th>Product Name</th>
            <th>Brand</th>
            <th>Quantity</th>
            <th>Unit Price</th>
            <th>Total Sales</th>
            <th>Profit</th>
          </tr>
        </thead>
        <tbody>
    `;
    
    // Add product rows (limit to top 20)
    const topProducts = reportData.products.slice(0, 20);
    topProducts.forEach(p => {
      htmlContent += `
      <tr>
        <td>${p.upc || 'N/A'}</td>
        <td>${p.name || 'N/A'}</td>
        <td>${p.brand || 'N/A'}</td>
        <td>${p.quantity || '0'}</td>
        <td>$${(p.price || 0).toFixed(2)}</td>
        <td>$${(p.totalSales || 0).toFixed(2)}</td>
        <td>$${(p.profit || 0).toFixed(2)}</td>
      </tr>
      `;
    });
    
    // Close the HTML
    htmlContent += `
        </tbody>
      </table>
      
      <div class="footer">
        © ${new Date().getFullYear()} VEND LAS VEGAS. All rights reserved.
      </div>
    </body>
    </html>
    `;
    
    // Create a temporary file with the HTML content
    const htmlFile = DriveApp.createFile('temp_report.html', htmlContent, 'text/html');
    
    // Convert to PDF using Google Docs
    const blob = htmlFile.getAs('application/pdf').setName(fileName);
    const pdfFile = DriveApp.createFile(blob);
    
    // Clean up the temporary HTML file
    htmlFile.setTrashed(true);
    
    // Get the PDF URL
    const pdfUrl = pdfFile.getUrl();
    
    console.log('HTML-styled PDF export completed successfully');
    return pdfUrl;
  } catch (e) {
    console.error('Error exporting product report to HTML PDF:', e);
    console.error('Stack trace:', e.stack);
    return null;
  }
}

/**
 * Formats a date as MM/DD/YYYY.
 * @param {Date} date The date to format.
 * @return {string} The formatted date.
 */
function formatDate(date) {
  return Utilities.formatDate(date, Session.getScriptTimeZone(), 'MM/dd/yyyy');
}

/**
 * Formats a time as HH:MM:SS.
 * @param {Date} date The date to extract time from.
 * @return {string} The formatted time.
 */
function formatTime(date) {
  return Utilities.formatDate(date, Session.getScriptTimeZone(), 'HH:mm:ss');
}

/**
 * Tests login credentials and returns detailed information.
 * This is for debugging purposes only.
 * @param {string} username The username to test.
 * @param {string} password The password to test.
 * @return {Object} Detailed login test results.
 */
function testLogin(username, password) {
  try {
    if (!username || !password) {
      return { 
        success: false, 
        message: 'Username or password is empty',
        details: { username: !!username, password: !!password }
      };
    }
    
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const loginSheet = ss.getSheetByName(LOGIN_SHEET_NAME);
    
    if (!loginSheet) {
      return { 
        success: false, 
        message: 'Login sheet not found.' 
      };
    }
    
    // Check master password
    const masterPassword = loginSheet.getRange('F1').getValue();
    const masterMatch = password === masterPassword;
    
    // Check user credentials
    const data = loginSheet.getDataRange().getValues();
    const users = [];
    let userMatch = false;
    let matchedUser = null;
    
    for (let i = 1; i < data.length; i++) {
      if (data[i].length >= 2) {
        const rowUsername = String(data[i][0]).trim();
        const rowPassword = String(data[i][1]).trim();
        
        users.push({
          username: rowUsername,
          usernameMatch: rowUsername === username,
          passwordMatch: rowPassword === password,
          fullMatch: rowUsername === username && rowPassword === password
        });
        
        if (rowUsername === username && rowPassword === password) {
          userMatch = true;
          matchedUser = rowUsername;
        }
      }
    }
    
    return {
      success: masterMatch || userMatch,
      message: masterMatch ? 'Master password match' : 
               userMatch ? `User match: ${matchedUser}` : 'No match found',
      details: {
        masterPassword: {
          exists: !!masterPassword,
          match: masterMatch
        },
        userCredentials: {
          count: users.length,
          match: userMatch,
          matchedUser: matchedUser,
          users: users
        }
      }
    };
  } catch (e) {
    return { 
      success: false, 
      message: 'Error testing login: ' + e.message,
      error: e.toString()
    };
  }
}
/**
 * Debug function to check the master password location.
 * @return {Object} Information about the master password location.
 */
function debugMasterPassword() {
  try {
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const loginSheet = ss.getSheetByName(LOGIN_SHEET_NAME);
    
    if (!loginSheet) {
      return { success: false, message: 'Login sheet not found.' };
    }
    
    // Check various possible locations
    const f1Value = loginSheet.getRange('F1').getValue();
    const f2Value = loginSheet.getRange('F2').getValue();
    const a1Value = loginSheet.getRange('A1').getValue();
    
    // Check the first few rows to find potential password locations
    const firstRows = loginSheet.getRange('A1:G5').getValues();
    
    return {
      success: true,
      locations: {
        'F1': f1Value,
        'F2': f2Value,
        'A1': a1Value
      },
      firstRows: firstRows
    };
  } catch (e) {
    return { success: false, message: 'Error: ' + e.message };
  }
}

// Schedule Management Functions
function getHoursOfOperation() {
  try {
    const ss = getSpreadsheet();
    const sheet = ss.getSheetByName('Hours') || ss.insertSheet('Hours');
    
    // Check if the sheet has the expected structure, if not, initialize it
    if (sheet.getLastRow() < 8) { // At least header + 7 days
      // Initialize the hours sheet with headers
      sheet.getRange('A1').setValue('Hours of Operation');
      sheet.getRange('A2:A8').setValues([['Sunday'], ['Monday'], ['Tuesday'], ['Wednesday'], ['Thursday'], ['Friday'], ['Saturday']]);
      sheet.getRange('B1').setValue('Open Time');
      sheet.getRange('C1').setValue('Close Time');
      sheet.getRange('D1').setValue('Closed');
    }
    
    // Get the data
    const daysRange = sheet.getRange('A2:A8').getValues();
    const openTimeRange = sheet.getRange('B2:B8').getValues();
    const closeTimeRange = sheet.getRange('C2:C8').getValues();
    const closedRange = sheet.getRange('D2:D8').getValues();
    
    // Format the data
    const hoursData = [];
    for (let i = 0; i < 7; i++) {
      hoursData.push({
        day: daysRange[i][0],
        openTime: openTimeRange[i][0] ? formatTime(openTimeRange[i][0]) : '',
        closeTime: closeTimeRange[i][0] ? formatTime(closeTimeRange[i][0]) : '',
        closed: closedRange[i][0] === true
      });
    }
    
    return { success: true, data: hoursData };
  } catch (error) {
    console.error('Error getting hours of operation:', error);
    return { success: false, message: 'Error getting hours of operation: ' + error.toString() };
  }
}

function updateHoursOfOperation(hoursData) {
  try {
    const ss = getSpreadsheet();
    const sheet = ss.getSheetByName('Hours');
    
    if (!sheet) {
      return { success: false, message: 'Hours sheet not found' };
    }
    
    // Update each day's data
    for (let i = 0; i < hoursData.length; i++) {
      const day = hoursData[i];
      const rowIndex = i + 2; // +2 because data starts at row 2
      
      // Convert time strings to Date objects if they're not empty
      let openTime = day.openTime ? parseTimeString(day.openTime) : '';
      let closeTime = day.closeTime ? parseTimeString(day.closeTime) : '';
      
      sheet.getRange(rowIndex, 2).setValue(openTime); // Open Time
      sheet.getRange(rowIndex, 3).setValue(closeTime); // Close Time
      sheet.getRange(rowIndex, 4).setValue(day.closed); // Closed checkbox
    }
    
    return { success: true, message: 'Hours of operation updated successfully' };
  } catch (error) {
    console.error('Error updating hours of operation:', error);
    return { success: false, message: 'Error updating hours of operation: ' + error.toString() };
  }
}

// Helper function to format time for display
function formatTime(timeValue) {
  if (!timeValue) return '';
  
  try {
    // If it's already a string in the right format, return it
    if (typeof timeValue === 'string') return timeValue;
    
    // If it's a Date object, format it
    if (timeValue instanceof Date) {
      const hours = timeValue.getHours();
      const minutes = timeValue.getMinutes();
      const ampm = hours >= 12 ? 'PM' : 'AM';
      const formattedHours = hours % 12 || 12;
      const formattedMinutes = minutes.toString().padStart(2, '0');
      return `${formattedHours}:${formattedMinutes} ${ampm}`;
    }
    
    return '';
  } catch (e) {
    console.error('Error formatting time:', e);
    return '';
  }
}

// Helper function to parse time string into Date object
function parseTimeString(timeString) {
  if (!timeString) return null;
  
  try {
    // Create a base date (today)
    const date = new Date();
    date.setHours(0, 0, 0, 0); // Reset to midnight
    
    // Parse the time string (assuming format like "9:00 AM" or "6:00 PM")
    const parts = timeString.match(/(\d+):(\d+)\s*(AM|PM)/i);
    if (!parts) return null;
    
    let hours = parseInt(parts[1], 10);
    const minutes = parseInt(parts[2], 10);
    const ampm = parts[3].toUpperCase();
    
    // Convert to 24-hour format
    if (ampm === 'PM' && hours < 12) hours += 12;
    if (ampm === 'AM' && hours === 12) hours = 0;
    
    date.setHours(hours, minutes);
    return date;
  } catch (e) {
    console.error('Error parsing time string:', e);
    return null;
  }
}

// Add these to your Code.gs file
function lookupProduct(upc) {
  return lookupUpcForWebApp(upc);
}

function requestProductInfo(upc) {
  return requestInfoForWebApp(upc);
}

function saveProduct(product) {
  return saveProductFromWebApp(product);
}

