# This Python file uses the following encoding: utf-8
from multiprocessing import Process,Queue
import os
from pathlib import Path
import sys

from PySide6.QtWidgets import (QApplication, QWidget,QGridLayout,
                QHBoxLayout,QVBoxLayout,QLineEdit,QDialog,
                QGridLayout, QSpacerItem, QInputDialog, QFileDialog,
                QErrorMessage, QMessageBox)
from PySide6.QtCore import QFile,Slot,QObject,Signal,QThread
from PySide6.QtUiTools import QUiLoader
from PySide6.QtGui import QPalette, QTextCursor

import numpy as np

from scipy.io import loadmat
from matplotlib.pyplot import cm
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import (
    FigureCanvas,NavigationToolbar2QT)

#import cv2 as cv
import os
import sys
import shutil
from datetime import datetime
import time
import yaml
from BabelViscoFDTD.H5pySimple import ReadFromH5py, SaveToH5py
from GUIComponents.ScrollBars import ScrollBars as WidgetScrollBars

from .CalculateFieldProcess import CalculateFieldProcess

from _BabelBaseTx import BabelBaseTx

class H317(BabelBaseTx):
    def __init__(self,parent=None,MainApp=None):
        super(H317, self).__init__(parent)
        self.static_canvas=None
        self._MainApp=MainApp
        self.DefaultConfig()
        self.load_ui()


    def load_ui(self):
        loader = QUiLoader()
        path = os.fspath(Path(__file__).resolve().parent / "form.ui")
        ui_file = QFile(path)
        ui_file.open(QFile.ReadOnly)
        self.Widget =loader.load(ui_file, self)
        ui_file.close()

        self.Widget.IsppaScrollBars = WidgetScrollBars(parent=self.Widget.IsppaScrollBars,MainApp=self)

        self.Widget.ZSteeringSpinBox.setMinimum(self.Config['MinimalZSteering']*1e3)
        self.Widget.ZSteeringSpinBox.setMaximum(self.Config['MaximalZSteering']*1e3)
        self.Widget.ZSteeringSpinBox.setValue(0.0)

        self.Widget.DistanceConeToFocusSpinBox.setMinimum(self.Config['MinimalDistanceConeToFocus']*1e3)
        self.Widget.DistanceConeToFocusSpinBox.setMaximum(self.Config['MaximalDistanceConeToFocus']*1e3)
        self.Widget.DistanceConeToFocusSpinBox.setValue(self.Config['DefaultDistanceConeToFocus']*1e3)

        self.Widget.ZSteeringSpinBox.valueChanged.connect(self.ZSteeringUpdate)
        self.Widget.RefocusingcheckBox.stateChanged.connect(self.EnableRefocusing)
        self.Widget.CalculatePlanningMask.clicked.connect(self.RunSimulation)
        self.up_load_ui()
       
    @Slot()
    def ZSteeringUpdate(self,value):
        self._ZSteering =self.Widget.ZSteeringSpinBox.value()/1e3

    @Slot()
    def EnableRefocusing(self,value):
        bRefocus =self.Widget.RefocusingcheckBox.isChecked()
        self.Widget.XMechanicSpinBox.setEnabled(not bRefocus)
        self.Widget.YMechanicSpinBox.setEnabled(not bRefocus)
        self.Widget.ZMechanicSpinBox.setEnabled(not bRefocus)

    def DefaultConfig(self):
        #Specific parameters for the H317 - to be configured later via a yaml

        with open(os.path.join(os.path.dirname(os.path.realpath(__file__)),'default.yaml'), 'r') as file:
            config = yaml.safe_load(file)
        print("H317 configuration:")
        print(config)

        self.Config=config

    def NotifyGeneratedMask(self):
        VoxelSize=self._MainApp._DataMask.header.get_zooms()[0]
        TargetLocation =np.array(np.where(self._MainApp._FinalMask==5.0)).flatten()
        LineOfSight=self._MainApp._FinalMask[TargetLocation[0],TargetLocation[1],:]
        StartSkin=np.where(LineOfSight>0)[0].min()
        DistanceFromSkin = (TargetLocation[2]-StartSkin)*VoxelSize

        self.Widget.DistanceSkinLabel.setText('%3.2f'%(DistanceFromSkin))
        self.Widget.DistanceSkinLabel.setProperty('UserData',DistanceFromSkin)

        self.ZSteeringUpdate(0)

    @Slot()
    def RunSimulation(self):
        self._FullSolName=self._MainApp._prefix_path+'DataForSim.h5'
        self._WaterSolName=self._MainApp._prefix_path+'Water_DataForSim.h5'

        print('FullSolName',self._FullSolName)
        print('WaterSolName',self._WaterSolName)
        bCalcFields=False
        if os.path.isfile(self._FullSolName) and os.path.isfile(self._WaterSolName):
            Skull=ReadFromH5py(self._FullSolName)
            ZSteering=Skull['ZSteering']
            if 'RotationZ' in Skull:
                RotationZ=Skull['RotationZ']
            else:
                RotationZ=0.0

            ret = QMessageBox.question(self,'', "Acoustic sim files already exist with:.\n"+
                                    "ZSteering=%3.2f\n" %(ZSteering*1e3)+
                                    "ZRotation=%3.2f\n" %(RotationZ)+
                                    "TxMechanicalAdjustmentX=%3.2f\n" %(Skull['TxMechanicalAdjustmentX']*1e3)+
                                    "TxMechanicalAdjustmentY=%3.2f\n" %(Skull['TxMechanicalAdjustmentY']*1e3)+
                                    "TxMechanicalAdjustmentZ=%3.2f\n" %(Skull['TxMechanicalAdjustmentZ']*1e3)+
                                    "Do you want to recalculate?\nSelect No to reload",
                QMessageBox.Yes | QMessageBox.No)

            if ret == QMessageBox.Yes:
                bCalcFields=True
            else:
                self.Widget.ZSteeringSpinBox.setValue(ZSteering*1e3)
                self.Widget.ZRotationSpinBox.setValue(RotationZ)
                self.Widget.RefocusingcheckBox.setChecked(Skull['bDoRefocusing'])
                if 'DistanceConeToFocus' in Skull:
                    self.Widget.DistanceConeToFocusSpinBox.setValue(Skull['DistanceConeToFocus']*1e3)
                self.Widget.XMechanicSpinBox.setValue(Skull['TxMechanicalAdjustmentX']*1e3)
                self.Widget.YMechanicSpinBox.setValue(Skull['TxMechanicalAdjustmentY']*1e3)
                self.Widget.ZMechanicSpinBox.setValue(Skull['TxMechanicalAdjustmentZ']*1e3)
        else:
            bCalcFields = True
        self._bRecalculated = True
        if bCalcFields:
            self._MainApp.Widget.tabWidget.setEnabled(False)
            self.thread = QThread()
            self.worker = RunAcousticSim(self._MainApp,self.thread)
            self.worker.moveToThread(self.thread)
            self.thread.started.connect(self.worker.run)
            self.worker.finished.connect(self.UpdateAcResults)
            self.worker.finished.connect(self.thread.quit)
            self.worker.finished.connect(self.worker.deleteLater)
            self.thread.finished.connect(self.thread.deleteLater)

            self.worker.endError.connect(self.NotifyError)
            self.worker.endError.connect(self.thread.quit)
            self.worker.endError.connect(self.worker.deleteLater)
            self.thread.start()
        else:
            self.UpdateAcResults()

    def NotifyError(self):
        msgBox = QMessageBox()
        msgBox.setIcon(QMessageBox.Critical)
        msgBox.setText("There was an error in execution -\nconsult log window for details")
        msgBox.exec()

    def GetExport(self):
        Export={}
        Export['Refocusing']=self.Widget.RefocusingcheckBox.isChecked()
        for k in ['ZSteering','ZRotation','DistanceConeToFocus','XMechanic','YMechanic','ZMechanic']:
            Export[k]=getattr(self.Widget,k+'SpinBox').value()
        return Export

    @Slot()
    def UpdateAcResults(self):
        #We overwrite the base class method
        if self._bRecalculated:
            #this will generate a modified trajectory file
            if self.Widget.ShowWaterResultscheckBox.isEnabled()== False:
                self.Widget.ShowWaterResultscheckBox.setEnabled(True)
            if self.Widget.HideMarkscheckBox.isEnabled()== False:
                self.Widget.HideMarkscheckBox.setEnabled(True)
            self._MainApp.Widget.tabWidget.setEnabled(True)
            self._MainApp.ThermalSim.setEnabled(True)
            Water=ReadFromH5py(self._WaterSolName)
            Skull=ReadFromH5py(self._FullSolName)
            if self._MainApp._bInUseWithBrainsight:
                if Skull['bDoRefocusing']:
                    #we update the name to be loaded in BSight
                    self._MainApp._BrainsightInput=self._MainApp._prefix_path+'FullElasticSolutionRefocus.nii.gz'
                with open(self._MainApp._BrainsightSyncPath+os.sep+'Output.txt','w') as f:
                    f.write(self._MainApp._BrainsightInput) 
            self._MainApp.ExportTrajectory(CorX=Skull['AdjustmentInRAS'][0],
                                        CorY=Skull['AdjustmentInRAS'][1],
                                        CorZ=Skull['AdjustmentInRAS'][2])

            LocTarget=Skull['TargetLocation']
            print(LocTarget)

            if Skull['bDoRefocusing']:
                SelP='p_amp_refocus'
            else:
                SelP='p_amp'

            for d in [Skull]:
                for t in [SelP,'MaterialMap']:
                    d[t]=np.ascontiguousarray(np.flip(d[t],axis=2))

            for d in [Water]:
                for t in ['p_amp','MaterialMap']:
                    d[t]=np.ascontiguousarray(np.flip(d[t],axis=2))

            DistanceToTarget=self.Widget.DistanceSkinLabel.property('UserData')

            Water['z_vec']*=1e3
            Skull['z_vec']*=1e3
            Skull['x_vec']*=1e3
            Skull['y_vec']*=1e3
            Skull['MaterialMap'][Skull['MaterialMap']==3]=2
            Skull['MaterialMap'][Skull['MaterialMap']==4]=3


            IWater=Water['p_amp']**2/2/Water['Material'][0,0]/Water['Material'][0,1]

            DensityMap=Skull['Material'][:,0][Skull['MaterialMap']]
            SoSMap=    Skull['Material'][:,1][Skull['MaterialMap']]
            ISkull=Skull[SelP]**2/2/DensityMap/SoSMap/1e4

            IntWaterLocation=IWater[LocTarget[0],LocTarget[1],LocTarget[2]]
            IntSkullLocation=ISkull[LocTarget[0],LocTarget[1],LocTarget[2]]

            EnergyAtFocusWater=IWater[:,:,LocTarget[2]].sum()
            EnergyAtFocusSkull=ISkull[:,:,LocTarget[2]].sum()

            ISkull/=ISkull[Skull['MaterialMap']==3].max()
            IWater/=IWater[Skull['MaterialMap']==3].max()

            Factor=EnergyAtFocusWater/EnergyAtFocusSkull
            
            ISkull[Skull['MaterialMap']!=3]=0

            dz=np.diff(Skull['z_vec']).mean()
            Zvec=Skull['z_vec'].copy()
            Zvec-=Zvec[LocTarget[2]]
            Zvec+=DistanceToTarget#+self.Widget.ZSteeringSpinBox.value()
            XX,ZZ=np.meshgrid(Skull['x_vec'],Zvec)
            self._XX = XX
            self._ZZX = ZZ
            YY,ZZ=np.meshgrid(Skull['y_vec'],Zvec)
            self._YY = YY
            self._ZZY = ZZ

            self.Widget.IsppaScrollBars.set_default_values(LocTarget,Skull['x_vec']-Skull['x_vec'][LocTarget[0]],Skull['y_vec']-Skull['y_vec'][LocTarget[1]])

            self._Water = Water
            self._IWater = IWater/IWater.max()
            self._Skull = Skull
            self._ISkull = ISkull/ISkull.max()
            self._DistanceToTarget = DistanceToTarget

            if hasattr(self,'_figAcField'):
                children = []
                for i in range(self._layout.count()):
                    child = self._layout.itemAt(i).widget()
                    if child:
                        children.append(child)
                for child in children:
                    child.deleteLater()
                delattr(self,'_figAcField')
                self.Widget.AcField_plot1.repaint()
        
        SelY, SelX = self.Widget.IsppaScrollBars.get_scroll_values()

        if self.Widget.ShowWaterResultscheckBox.isChecked():
            sliceXZ=self._IWater[:,SelY,:]
            sliceYZ = self._IWater[SelX,:,:]
        else:
            sliceXZ=self._ISkull[:,SelY,:]
            sliceYZ = self._ISkull[SelX,:,:]

        if hasattr(self,'_figAcField'):
            if hasattr(self,'_imContourf1'):
                for c in [self._imContourf1,self._imContourf2,self._contour1,self._contour2]:
                    for coll in c.collections:
                        coll.remove()
                del self._imContourf1
                del self._imContourf2
                del self._contour1
                del self._contour2

            self._imContourf1=self._static_ax1.contourf(self._XX,self._ZZX,sliceXZ.T,np.arange(2,22,2)/20,cmap=plt.cm.jet)
            self._contour1 = self._static_ax1.contour(self._XX,self._ZZX,self._Skull['MaterialMap'][:,SelY,:].T,[0,1,2,3], cmap=plt.cm.gray)

            self._imContourf2=self._static_ax2.contourf(self._YY,self._ZZY,sliceYZ.T,np.arange(2,22,2)/20,cmap=plt.cm.jet)
            self._contour2 = self._static_ax2.contour(self._YY,self._ZZY,self._Skull['MaterialMap'][SelX,:,:].T,[0,1,2,3], cmap=plt.cm.gray)

            self._figAcField.canvas.draw_idle()
        else:
            self._figAcField=Figure(figsize=(14, 12))

            if not hasattr(self,'_layout'):
                self._layout = QVBoxLayout(self.Widget.AcField_plot1)

            self.static_canvas = FigureCanvas(self._figAcField)
            toolbar=NavigationToolbar2QT(self.static_canvas,self)
            self._layout.addWidget(toolbar)
            self._layout.addWidget(self.static_canvas)
            static_ax1,static_ax2 = self.static_canvas.figure.subplots(1,2)
            self._static_ax1 = static_ax1
            self._static_ax2 = static_ax2

            self._imContourf1=static_ax1.contourf(self._XX,self._ZZX,sliceXZ.T,np.arange(2,22,2)/20,cmap=plt.cm.jet)
            h=plt.colorbar(self._imContourf1,ax=static_ax1)
            h.set_label('$I_{\mathrm{SPPA}}$ (normalized)')
            self._contour1 = static_ax1.contour(self._XX,self._ZZX,self._Skull['MaterialMap'][:,SelY,:].T,[0,1,2,3], cmap=plt.cm.gray)
            static_ax1.set_aspect('equal')
            static_ax1.set_xlabel('X mm')
            static_ax1.set_ylabel('Z mm')
            static_ax1.invert_yaxis()
            self._marker1,=static_ax1.plot(0,self._DistanceToTarget,'+k',markersize=18)
                
            self._imContourf2=static_ax2.contourf(self._YY,self._ZZY,sliceYZ.T,np.arange(2,22,2)/20,cmap=plt.cm.jet)
            h=plt.colorbar(self._imContourf1,ax=static_ax2)
            h.set_label('$I_{\mathrm{SPPA}}$ (normalized)')
            self._contour2 = static_ax2.contour(self._YY,self._ZZY,self._Skull['MaterialMap'][SelX,:,:].T,[0,1,2,3], cmap=plt.cm.gray)
            static_ax2.set_aspect('equal')
            static_ax2.set_xlabel('Y mm')
            static_ax2.set_ylabel('Z mm')
            static_ax2.invert_yaxis()
            self._marker2,=static_ax2.plot(0,self._DistanceToTarget,'+k',markersize=18)
        
        self._figAcField.set_facecolor(np.array(self.Widget.palette().color(QPalette.Window).getRgb())/255)

        mc=[0.0,0.0,0.0,1.0]
        if self.Widget.HideMarkscheckBox.isChecked():
             mc[3] = 0.0
        self._marker1.set_markerfacecolor(mc)
        self._marker2.set_markerfacecolor(mc)

        self.Widget.IsppaScrollBars.update_labels(SelX, SelY)
        self._bRecalculated = False


class RunAcousticSim(QObject):

    finished = Signal()
    endError = Signal()

    def __init__(self,mainApp,thread):
        super(RunAcousticSim, self).__init__()
        self._mainApp=mainApp
        self._thread=thread

    def run(self):

        deviceName=self._mainApp.Config['ComputingDevice']
        COMPUTING_BACKEND=self._mainApp.Config['ComputingBackend']
        basedir,ID=os.path.split(os.path.split(self._mainApp.Config['T1W'])[0])
        basedir+=os.sep
        Target=[self._mainApp.Config['ID']+'_'+self._mainApp.Config['TxSystem']]

        InputSim=self._mainApp._outnameMask

        bRefocus = self._mainApp.AcSim.Widget.RefocusingcheckBox.isChecked()
        #we can use mechanical adjustments in other directions for final tuning
        if not bRefocus:
            TxMechanicalAdjustmentX= self._mainApp.AcSim.Widget.XMechanicSpinBox.value()/1e3 #in m
            TxMechanicalAdjustmentY= self._mainApp.AcSim.Widget.YMechanicSpinBox.value()/1e3  #in m
            TxMechanicalAdjustmentZ= self._mainApp.AcSim.Widget.ZMechanicSpinBox.value()/1e3  #in m

        else:
            TxMechanicalAdjustmentX=0
            TxMechanicalAdjustmentY=0
            TxMechanicalAdjustmentZ=0
        ###############
        ZSteering=self._mainApp.AcSim.Widget.ZSteeringSpinBox.value()/1e3  #Add here the final adjustment)
        XSteering=1e-6
        ##############
        RotationZ=self._mainApp.AcSim.Widget.ZRotationSpinBox.value()

        print('ZSteering',ZSteering*1e3)
        print('RotationZ',RotationZ)

        Frequencies = [self._mainApp.Widget.USMaskkHzDropDown.property('UserData')]
        basePPW=[self._mainApp.Widget.USPPWSpinBox.property('UserData')]
        T0=time.time()

        DistanceConeToFocus=self._mainApp.AcSim.Widget.DistanceConeToFocusSpinBox.value()/1e3

        kargs={}
        kargs['ID']=ID
        kargs['deviceName']=deviceName
        kargs['COMPUTING_BACKEND']=COMPUTING_BACKEND
        kargs['basePPW']=basePPW
        kargs['basedir']=basedir
        kargs['TxMechanicalAdjustmentZ']=TxMechanicalAdjustmentZ
        kargs['TxMechanicalAdjustmentX']=TxMechanicalAdjustmentX
        kargs['TxMechanicalAdjustmentY']=TxMechanicalAdjustmentY
        kargs['XSteering']=XSteering
        kargs['ZSteering']=ZSteering
        kargs['RotationZ']=RotationZ
        kargs['Frequencies']=Frequencies
        kargs['zLengthBeyonFocalPointWhenNarrow']=self._mainApp.AcSim.Widget.MaxDepthSpinBox.value()/1e3
        kargs['bDoRefocusing']=bRefocus
        kargs['DistanceConeToFocus']=DistanceConeToFocus
        kargs['bUseCT']=self._mainApp.Config['bUseCT']

        # Start mask generation as separate process.
        queue=Queue()
        fieldWorkerProcess = Process(target=CalculateFieldProcess, 
                                    args=(queue,Target),
                                    kwargs=kargs)
        fieldWorkerProcess.start()      
        # progress.
        T0=time.time()
        bNoError=True
        while fieldWorkerProcess.is_alive():
            time.sleep(0.1)
            while queue.empty() == False:
                cMsg=queue.get()
                print(cMsg,end='')
                if '--Babel-Brain-Low-Error' in cMsg:
                    bNoError=False  
        fieldWorkerProcess.join()
        while queue.empty() == False:
            cMsg=queue.get()
            print(cMsg,end='')
            if '--Babel-Brain-Low-Error' in cMsg:
                bNoError=False
        if bNoError:
            TEnd=time.time()
            print('Total time',TEnd-T0)
            print("*"*40)
            print("*"*5+" DONE ultrasound simulation.")
            print("*"*40)
            self.finished.emit()
        else:
            print("*"*40)
            print("*"*5+" Error in execution.")
            print("*"*40)
            self.endError.emit()


if __name__ == "__main__":
    app = QApplication([])
    widget = H317()
    widget.show()
    sys.exit(app.exec_())
