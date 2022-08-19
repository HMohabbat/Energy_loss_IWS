#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri Aug 13 14:56:07 2021

@author: hamid
"""
#the following script relys on an early development of IWS-izing WDNs. The assumptions are:
    #consumers will draw as much as water as possible. 
    
    
import wntr
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import os 
import shutil




leakage_rate_list=[0.05,0.15,0.45,0.60]
frequency=1
timestep=60
demand_rate=0.85
LPS_to_CMPD=86.4
assumed_pressure=30
pipe_diameter_power=0.38
minor_energy_loss_power=-0.479
day=86400
name_list=['MOD']
root=os.getcwd()

    
for name in name_list:
    root=root+'/'+name+'/STM'  
    
    if os.path.exists(root):
        shutil.rmtree(root)
    os.makedirs(root)
    
    link_address='root_networks/'+name+'.inp'
    
    volume_received_per_leakage_rate=pd.DataFrame(data=None, columns=leakage_rate_list)
    volume_leaked_per_leakage_rate=pd.DataFrame(data=None, columns=leakage_rate_list)
    volume_input_per_leakage_rate=pd.DataFrame(data=None, columns=leakage_rate_list)

    peak_input_flowrate_per_leakage_rate=pd.DataFrame(data=None, columns=leakage_rate_list)
    peak_received_flowrate_per_leakage_rate=pd.DataFrame(data=None, columns=leakage_rate_list)
    peak_leaked_flowrate_per_leakage_rate=pd.DataFrame(data=None, columns=leakage_rate_list)
    
    energyloss_per_leakage_rate=pd.DataFrame(data=None, columns=leakage_rate_list)
    peak_powerloss_per_leakage_rate=pd.DataFrame(data=None, columns=leakage_rate_list)
    
    for leakage_rate in leakage_rate_list:
        
        path=root+'/'+str(leakage_rate)
        if os.path.exists(path):
            shutil.rmtree(path)
        os.makedirs(path)
        
        path2=root+'/Comparison between different leakage rates'
        if os.path.exists(path2):
            shutil.rmtree(path2)
        os.makedirs(path2)

        subpath1=path+'/generated_networks'
        if os.path.exists(subpath1):
            shutil.rmtree(subpath1)
        os.makedirs(subpath1)
        
        subpath2=path+'/final_results'
        
        if os.path.exists(subpath2):
            shutil.rmtree(subpath2)
        os.makedirs(subpath2)
        
        ## SECTION #1: Turning the CWS into IWS networks assuming using Simple tanks method in (Taylor et al. 2019)
        # Openeing the .inp file of CWS and simulating it using the EPANET
        CWS=wntr.network.WaterNetworkModel (inp_file_name=link_address)
        results_CWS=wntr.sim.EpanetSimulator(CWS).run_sim()
        
        # For simulating leakage, emitters will be used. But first, their coefficients are calculated: 
            #The emitter coefficient will be caluculated based on the average pressure through network:
        mean_network_CWS=results_CWS.node['pressure'].drop(columns=CWS.reservoir_name_list).mean().mean()
            #Only junctions with demand (non_zero) demand will be taken into account
            
        demands_CWS=results_CWS.node['demand']
        zero_demand_nodes=[]
        
        for i in demands_CWS.columns:
            if demands_CWS[i].any()==0:
                zero_demand_nodes=zero_demand_nodes+[i]      


        demands_CWS=demands_CWS.drop(columns=CWS.reservoir_name_list+zero_demand_nodes)
        
        emitters_coefficient=leakage_rate*demands_CWS/assumed_pressure    
        emitter_list= ['Emit'+str(num) for num in demands_CWS.columns]
        emitters_coefficient.columns=emitter_list

        #adding emitters to the network, with the already calculated coefficients    
        for junction in demands_CWS.columns: 
           CWS.add_junction('Emit'+junction, base_demand= 0.00, elevation=CWS.nodes[junction].elevation,\
                           coordinates=tuple (np.subtract (CWS.nodes[junction].coordinates,(100,100))))
            
        for emitter in emitter_list:  
           CWS.nodes[str (emitter)].emitter_coefficient=float(emitters_coefficient[emitter])
            
        
        for t in demands_CWS.columns:
            diameter_average=0
            for link in CWS.get_links_for_node(t):
                diameter_average=diameter_average+CWS.get_link(link).diameter
            diameter_average=diameter_average/len (CWS.get_links_for_node(t))    
            CWS.add_pipe('AP2for'+t, t,'Emit'+t,length=1,diameter=diameter_average,roughness=130\
                         ,minor_loss=0,initial_status='CV',check_valve=True)    
        
        for junction in demands_CWS.columns:
            CWS.add_tank('AT'+junction, elevation=CWS.nodes[junction].elevation,init_level=0,min_level=0,max_level=1,\
                        diameter=np.sqrt (4*(demand_rate)*1000*demands_CWS[junction][0]*LPS_to_CMPD/np.pi/frequency),\
                           coordinates=tuple (np.add (CWS.nodes[junction].coordinates,(100,100))))
                
          
        for junction in demands_CWS.columns:
            CWS.add_pipe ('AP1for'+junction,junction, 'AT'+junction,length=10,diameter=15/1000*((CWS.get_node(junction).base_demand*1000*LPS_to_CMPD)**(pipe_diameter_power))\
                          ,roughness=130,minor_loss=8*(CWS.get_node(junction).base_demand*1000*LPS_to_CMPD)**(minor_energy_loss_power),initial_status='CV',check_valve=True)
             #removing the demands for nodes for all of the nodes, only base values of the demand time series is set to zero
            CWS.nodes[junction].demand_timeseries_list[0].base_value=0
        
        #The time options of the network is changed so it would fit in the extended period analysis\
            #of the IWS and the variation    
            CWS.options.hydraulic.emitter_exponent=1
            CWS.options.hydraulic.unbalanced='STOP'
            CWS.options.hydraulic.trials=500
            CWS.options.hydraulic.accuracy=0.001
            TimeOptions=CWS.options.time
            TimeOptions.duration=day
            TimeOptions.hydraulic_timestep=timestep
            TimeOptions.quality_timestep=300
            TimeOptions.rule_timestep=300
            TimeOptions.pattern_timestep=3600
            TimeOptions.report_timestep=timestep
            TimeOptions.report_start=0
            TimeOptions.start_clocktime=0
            TimeOptions.statistic='NONE'
          
        
        CWS.write_inpfile(subpath1+'/'+name+'_tankMethod'+str(leakage_rate)+'.inp',units='LPS')
            
        ##running an already Intermittent-ized system
        IWS=wntr.network.WaterNetworkModel (inp_file_name=subpath1+'/'+name+'_tankMethod'+str(leakage_rate)+'.inp')
        results=wntr.sim.EpanetSimulator(IWS).run_sim()
        
        emitter_list_found=[]
        for tank in IWS.tank_name_list:    
            emitter_list_found=emitter_list_found+[tank.replace('AT','Emit')]


        demands=results.node['demand']
        demands.index=demands.index/day #indexing based on hour
        
        volume_received=(demands[IWS.tank_name_list].cumsum().sum(axis=1))*timestep
        volume_input=-1*(demands[IWS.reservoir_name_list].cumsum().sum(axis=1))
        volume_leaked=(demands[emitter_list_found].cumsum().sum(axis=1))*timestep
                                                                                     
        (volume_received).to_excel(subpath2+'/'+str (leakage_rate)+'demand_satisfaction.xlsx')
        (volume_leaked).to_excel(subpath2+'/'+str (leakage_rate)+'leakage.xlsx')
        (volume_input).to_excel(subpath2+'/'+str (leakage_rate)+'total_input_volume.xlsx')
        
        volume_input_per_leakage_rate[leakage_rate]=volume_leaked
        volume_leaked_per_leakage_rate[leakage_rate]=volume_leaked
        volume_received_per_leakage_rate[leakage_rate]=volume_received
        

        peak_input_flow_rate=((-1*(demands[IWS.reservoir_name_list].sum(axis=1))).max())
        peak_received_flow_rate=(demands[IWS.tank_name_list].sum(axis=1)).max()
        peak_leaked_flow_rate=demands[emitter_list_found].sum(axis=1)
        
        peak_input_flow_rate_dataframe=pd.DataFrame(data=[peak_input_flow_rate]*int(day/timestep+1),index=demands.index)
        peak_received_flow_rate_dataframe=pd.DataFrame(data=[peak_received_flow_rate]*(int(day/timestep)+1), index=demands.index)

        peak_input_flowrate_per_leakage_rate[leakage_rate]=peak_input_flow_rate_dataframe
        peak_received_flowrate_per_leakage_rate[leakage_rate]=peak_received_flow_rate_dataframe
        peak_leaked_flowrate_per_leakage_rate[leakage_rate]=peak_leaked_flow_rate
        
        pressure=results.node['pressure']
        pressure.index=pressure.index/day
        
        headloss=results.link['headloss'].drop(columns=CWS.pump_name_list)
        headloss.index=headloss.index/day
        
        flowrate=results.link['flowrate'].abs().drop(columns=CWS.pump_name_list)
        flowrate.index=flowrate.index/day
                                                               
        
        tank_pressure=pressure[IWS.tank_name_list]
        tank_pressure.to_excel(subpath2+'/tank_pressure_'+str(leakage_rate)+'.xlsx')
        
        stored_volume=pd.DataFrame(data=None, columns=IWS.tank_name_list)
    
        for tank in IWS.tank_name_list:
            stored_volume[tank]=(np.pi*(IWS.get_node(tank).diameter/2)**2*tank_pressure[tank])
        
        weighted_volume=stored_volume[tank_pressure>0.99].sum(axis=1)
        weighted_volume.to_excel(subpath2+'/weighted volume'+str(leakage_rate)+'.xlsx')

        energyloss=(headloss*flowrate).sum(axis=1).cumsum()*timestep
        (energyloss).to_excel(subpath2+'/energyloss_no_abs'+str(leakage_rate)+'.xlsx')
        
        energyloss_per_leakage_rate[leakage_rate]=energyloss
        
        peak_powerloss=(headloss*flowrate).sum(axis=1).max()
        peak_powerloss_dataframe=pd.DataFrame(data=[peak_powerloss]*(int(day/timestep)+1),index=demands.index)
        
        peak_powerloss_per_leakage_rate[leakage_rate]=peak_powerloss_dataframe
        
    volume_received_per_leakage_rate.to_excel(path2+'/Received Volume.xlsx')
    volume_leaked_per_leakage_rate.to_excel(path2+'/Leaked Volume.xlsx')
    volume_input_per_leakage_rate.to_excel(path2+'/Input Volume.xlsx')
    (volume_received_per_leakage_rate+volume_leaked_per_leakage_rate).to_excel(path2+'/Summation of Recevied and Input Volume.xlsx')

    peak_input_flowrate_per_leakage_rate.to_excel(path2+'/Peak Input Flowrate.xlsx')
    peak_received_flowrate_per_leakage_rate.to_excel(path2+'/Peak Received Flowrate.xlsx')
    peak_leaked_flowrate_per_leakage_rate.to_excel(path2+'/Peak Leaked Flowrate.xlsx')
    
    energyloss_per_leakage_rate.to_excel(path2+'/Energyloss.xlsx')
    peak_powerloss_per_leakage_rate.to_excel(path2+'/Peak Powerloss.xlsx')
        
        
        