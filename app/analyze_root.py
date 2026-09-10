#!/usr/bin/env python3

import ROOT
import sys
import os
import re

def analyze_root_file(file_path):
    
    if not os.path.exists(file_path):
        print(f"Error: File {file_path} does not exist!")
        return
    
    try:
        root_file = ROOT.TFile.Open(file_path)
        if not root_file or root_file.IsZombie():
            print(f"Error: Cannot open file {file_path}")
            return
        
        print(f"=== NanoAOD Analysis: {file_path} ===")
        print()

        print("Objects in ROOT file:")
        root_file.ls()
        print()
        
        trees = []
        for key in root_file.GetListOfKeys():
            obj = key.ReadObj()
            if obj.InheritsFrom("TTree"):
                trees.append(obj.GetName())
        
        if not trees:
            print("No TTree found in file!")
            return

        print(f"Found trees: {trees}")
        print()
        
        total_events = 0
        for tree_name in trees:
            tree = root_file.Get(tree_name)
            if tree:
                entries = tree.GetEntries()
                total_events += entries
                print(f"Tree '{tree_name}': {entries} events")
        
        print(f"\nTotal events in all trees: {total_events}")
        print()
        print("-" * 80)
        print()
        
        if "Events" in trees:
            print("=== PPS & Proton Variables Analysis (regex: *PPS* OR *proton*) ===")

            events_tree = root_file.Get("Events")
            if events_tree:
                try:
                    df = ROOT.RDataFrame("Events", file_path)
                    
                    columns = df.GetColumnNames()
                    
                    columns_list = list(columns)
                    pps_columns = []
                    pps_pattern = re.compile(r'.*(PPS|proton).*', re.IGNORECASE)
                    for col in columns_list:
                        col_str = str(col).replace("b'", "").replace("'", "")
                        if pps_pattern.match(col_str):
                            pps_columns.append(col_str)
                    
                    print(f"Found PPS & Proton variables ({len(pps_columns)}):")
                    print()
                    
                    if pps_columns:
                        for i, col in enumerate(pps_columns, 1):
                            print(f"  {i:2d}. {col}")
                        print()
                    else:
                        print("  No PPS or proton variables found in this file")
                        print("  This file may not contain PPS detector or proton data")
                        print()
                    
                    if pps_columns:
                        print("--- PPS & Proton Variables Data (first 5 events) ---")
                        tree = events_tree
                        total_entries = tree.GetEntries()
                        print()
                        
                        max_events_to_show = min(5, total_entries)
                        
                        for col in pps_columns:
                            print(f"=== Data for variable: {col} ===")
                            try:
                                branch = tree.GetBranch(col)
                                if not branch:
                                    print(f"Cannot find branch {col}")
                                    continue
                                
                                leaf = branch.GetLeaf(col)
                                if leaf:
                                    leaf_type = leaf.GetTypeName()
                                    print(f"Type: {leaf_type}")
                                
                                count_var = None
                                if "PPSLocalTrack_" in col:
                                    count_var = "nPPSLocalTrack"
                                elif "Proton_multiRP_" in col and col != "nProton_multiRP":
                                    count_var = "nProton_multiRP"
                                elif "Proton_singleRP_" in col and col != "nProton_singleRP":
                                    count_var = "nProton_singleRP"
                                elif "PPS" in col and (col.endswith("_x") or col.endswith("_y") or col.endswith("_z")):
                                    for pps_col in pps_columns:
                                        if pps_col.startswith("n") and pps_col[1:] in col:
                                            count_var = pps_col
                                            break
                                
                                print(f"First {max_events_to_show} events:")
                                
                                for event in range(max_events_to_show):
                                    tree.GetEntry(event)
                                    
                                    array_size = None
                                    if count_var:
                                        try:
                                            array_size = getattr(tree, count_var)
                                        except:
                                            pass
                                    
                                    try:
                                        value = getattr(tree, col)
                                        
                                        if hasattr(value, '__len__') and hasattr(value, '__getitem__'):  # Array-like object
                                            if array_size is not None:
                                                if array_size == 0:
                                                    print(f"  Event {event:2d}: []")
                                                else:
                                                    array_values = [value[i] for i in range(array_size)]
                                                    print(f"  Event {event:2d}: {array_values}")
                                            else:
                                                array_values = list(value)
                                                print(f"  Event {event:2d}: {array_values}")
                                        else:
                                            print(f"  Event {event:2d}: {value}")
                                    
                                    except Exception as e:
                                        print(f"  Event {event:2d}: <unable to read: {e}>")
                                
                                print()
                                
                            except Exception as e:
                                print(f"Error reading data for {col}: {e}")
                                print()

                    
                except Exception as e:
                    print(f"Error during PPS analysis: {e}")
            else:
                print("Cannot access Events tree")
            
            print("-" * 80)
            print()
        else:
            print("Events tree not found in file")
        
        root_file.Close()
        
    except Exception as e:
        print(f"Error during analysis: {e}")

def main():
    
    if len(sys.argv) != 2:
        print("Usage: python3 analyze_root.py <path_to_file.root>")
        return
    
    file_path = sys.argv[1]
    
    try:
        # Suppress ROOT warnings
        ROOT.gROOT.SetBatch(True)
        ROOT.gErrorIgnoreLevel = ROOT.kWarning
        
        # Disable verbose information about ROOT dictionaries
        ROOT.gROOT.ProcessLine("gSystem->RedirectOutput(\"/dev/null\", \"w\");")
        ROOT.gROOT.ProcessLine("gSystem->RedirectOutput(0);")
        
        print("ROOT was loaded successfully")
        print(f"ROOT version: {ROOT.gROOT.GetVersion()}")
        print()
    except Exception as e:
        print(f"Error: Unable to load ROOT: {e}")
        print("Make sure ROOT is installed and configured")
        return

    # Analyze file
    analyze_root_file(file_path)
    

if __name__ == "__main__":
    main()