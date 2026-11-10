"""Opt-in desktop integration test. All API interactions use a synthetic helper."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

@unittest.skipUnless(os.environ.get('RUN_QML_INTEGRATION') == '1' and shutil.which('qs'), 'Set RUN_QML_INTEGRATION=1 in an Omarchy desktop session')
class CreateUiTests(unittest.TestCase):
    def test_form_preserves_failed_save_then_updates_on_success(self):
        with tempfile.TemporaryDirectory(prefix='supplier-ui-test-') as tmp:
            root=Path(tmp)
            for name in ('Commons','Ui'):
                (root/name).symlink_to(Path('/usr/share/omarchy/shell')/name, target_is_directory=True)
            plugin=root/'plugin';plugin.mkdir()
            source=Path(__file__).parent
            shutil.copy2(source/'BarWidget.qml',plugin/'BarWidget.qml')
            shutil.copytree(source/'i18n',plugin/'i18n')
            (plugin/'suppliers.py').write_text('''import json,sys
p=json.load(sys.stdin)
if p['name']=='Fail supplier':
 print(json.dumps({'created':False,'error_code':'createPermission'}))
else:
 row={**p,'uuid':'00000000-0000-4000-8000-000000000001'}
 print(json.dumps({'created':True,'supplier':row,'report':{'suppliers':[row],'error':'','connected':True}}))
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
   item.startCreate()
   test.child(item,"supplierName").text="Fail supplier"
   test.child(item,"supplierEmail").text="orders@example.invalid"
   test.child(item,"supplierAddress").text="Line 1\\nLine 2"
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
   if(test.stage===0 && widget.createErrorCode === "createPermission") {
    test.check(widget.createVisible,"failed form must stay open")
    test.check(test.child(widget,"supplierName").text === "Fail supplier","name retained")
    test.check(test.child(widget,"supplierAddress").text === "Line 1\\nLine 2","address retained")
    test.stage=1
    test.child(widget,"supplierName").text="Example Supplier"
    widget.saveSupplier()
   } else if(test.stage===1 && widget.noticeCode === "createSaved") {
    test.check(!widget.createVisible,"success returns to list")
    test.check(widget.report.suppliers[0].name === "Example Supplier","list refreshed")
    test.check(test.child(widget,"supplierName").text === "","form cleared only after success")
    console.log("CREATE_UI_OK")
    Qt.quit()
   }
  }
 }
}
''')
            result=subprocess.run(['qs','-p',str(root),'--no-color'],capture_output=True,text=True,timeout=15)
            output=result.stdout+result.stderr
            self.assertNotIn('TEST_FAILED',output,output)
            self.assertIn('CREATE_UI_OK',output,output)
            self.assertNotIn('ReferenceError',output,output)
            self.assertNotIn('TypeError',output,output)

if __name__=='__main__': unittest.main()
