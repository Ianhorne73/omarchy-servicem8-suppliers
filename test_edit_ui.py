"""Opt-in desktop integration test. All API interactions use a synthetic helper."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

@unittest.skipUnless(os.environ.get('RUN_QML_INTEGRATION') == '1' and shutil.which('qs'), 'Set RUN_QML_INTEGRATION=1 in an Omarchy desktop session')
class EditUiTests(unittest.TestCase):
    def test_edit_prefill_failure_and_success(self):
        with tempfile.TemporaryDirectory(prefix='supplier-ui-test-') as tmp:
            root=Path(tmp)
            for name in ('Commons','Ui'):
                (root/name).symlink_to(Path('/usr/share/omarchy/shell')/name, target_is_directory=True)
            plugin=root/'plugin';plugin.mkdir()
            source=Path(__file__).parent
            shutil.copy2(source/'BarWidget.qml',plugin/'BarWidget.qml')
            shutil.copytree(source/'i18n',plugin/'i18n')
            (plugin/'suppliers.py').write_text('''import json,sys
assert sys.argv[1:]==['--edit']
payload=json.load(sys.stdin)
assert payload['confirmation']=='yes'
assert payload['uuid']=='00000000-0000-4000-8000-000000000001'
p=payload['fields']
if p['name']=='Fail supplier':
 print(json.dumps({'updated':False,'error_code':'editPermission'}))
else:
 row={**p,'uuid':'00000000-0000-4000-8000-000000000001'}
 print(json.dumps({'updated':True,'supplier':row,'report':{'suppliers':[row],'error':'','connected':True}}))
''')
            (root/'shell.qml').write_text('''import QtQuick
import Quickshell
ShellRoot {
 id: test
 property int stage: 0
 property int ticks: 0
 function child(item,name,seen) {
  if(!item) return null
  seen=seen || []
  if(seen.indexOf(item)>=0) return null
  seen.push(item)
  if(item.objectName === name) return item
  var keys=["data","children","contentItem"]
  for(var k=0;k<keys.length;k++) {
   var nodes=item[keys[k]]
   if(!nodes) continue
   if(nodes.length === undefined) nodes=[nodes]
   for(var i=0;i<nodes.length;i++) { var found=child(nodes[i],name,seen); if(found) return found }
  }
  return null
 }
 function check(condition,message) { if(!condition) { console.log("TEST_FAILED: " + message); Qt.quit() } }
 Loader {
  id: loader
  source: "plugin/BarWidget.qml"
  onLoaded: {
   var row={uuid:"00000000-0000-4000-8000-000000000001",name:"Original Supplier",email:"orders@example.invalid",phone:"123456",address:"Original address",account_number:"A1",business_number:"ABN1"}
   item.report={suppliers:[row],error:""}
   item.startEdit(row)
   test.check(test.child(item,"supplierName").text==="Original Supplier","name prefilled")
   test.check(test.child(item,"supplierAccount").text==="A1","account prefilled")
   test.check(test.child(item,"supplierBusiness").text==="ABN1","business number prefilled")
   test.check(!item.possibleDuplicate,"editing self must not trigger duplicate warning")
   test.child(item,"supplierName").text="Fail supplier"
   test.child(item,"supplierEmail").text="orders@example.invalid"
   test.child(item,"supplierAddress").text="Line 1\\nLine 2"
   item.saveSupplier()
   test.check(item.editReviewVisible && !item.busy,"review must open before any save")
   var confirm=test.child(item,"editConfirmation")
   var save=test.child(item,"saveSupplier")
   var bad=["","Yes","YES"," yes","yes ","yesterday"]
   for(var i=0;i<bad.length;i++) {
    confirm.text=bad[i]
    test.check(!save.enabled,"wrong confirmation disables save")
    item.saveSupplier()
    test.check(!item.busy,"wrong confirmation must not call helper")
   }
   confirm.text="yes"
   test.child(item,"supplierPhone").text="654321"
   test.check(confirm.text==="" && !item.editReviewVisible,"changing a field invalidates confirmation")
   item.saveSupplier()
   confirm.text="yes"
   item.close()
   test.check(confirm.text==="" && !item.editReviewVisible,"closing requires fresh confirmation")
   item.saveSupplier()
   confirm.text="yes"
   item.saveSupplier()
  }
 }
 Timer {
  interval: 100; running: true; repeat: true
  onTriggered: {
   test.ticks++
   if(test.ticks>80) { console.log("TEST_FAILED: timeout"); Qt.quit(); return }
   var widget=loader.item
   if(!widget || widget.busy) return
   if(test.stage===0 && widget.createErrorCode === "editPermission") {
    test.check(widget.createVisible,"failed form must stay open")
    test.check(test.child(widget,"supplierName").text === "Fail supplier","name retained")
    test.check(test.child(widget,"supplierAddress").text === "Line 1\\nLine 2","address retained")
    test.check(test.child(widget,"editConfirmation").text==="" && !widget.editReviewVisible,"failed save needs fresh confirmation")
    test.stage=1
    test.child(widget,"supplierName").text="Example Supplier"
    widget.saveSupplier()
    test.check(widget.editReviewVisible && !widget.busy,"retry requires another review")
    test.child(widget,"editConfirmation").text="yes"
    widget.saveSupplier()
   } else if(test.stage===1 && widget.noticeCode === "editSaved") {
    test.check(!widget.createVisible && widget.editingSupplier===null,"success returns to list and clears edit mode")
    test.check(widget.report.suppliers[0].name === "Example Supplier","list refreshed")
    test.check(test.child(widget,"supplierName").text === "","form cleared only after success")
    console.log("EDIT_UI_OK")
    Qt.quit()
   }
  }
 }
}
''')
            result=subprocess.run(['qs','-p',str(root),'--no-color'],capture_output=True,text=True,timeout=15)
            output=result.stdout+result.stderr
            self.assertNotIn('TEST_FAILED',output,output)
            self.assertIn('EDIT_UI_OK',output,output)
            self.assertNotIn('ReferenceError',output,output)
            self.assertNotIn('TypeError',output,output)

if __name__=='__main__': unittest.main()
