// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"

/**
 *
 */

class SMainWidget;

class UE5PROJECT_API FMainWidgetController
{
public:
	static FMainWidgetController* Get();
	
	void CreateMainWidget();
	void RemoveMainWidget() const;
protected:
	TSharedPtr<SMainWidget> MainWidget;

public:
	TPanelChildren<SOverlay::FOverlaySlot>::FScopedWidgetSlotArguments AddWidget() const;
	void AddWidget(const TSharedRef<SWidget>& InWidget) const;
	void RemoveWidget(const TSharedRef<SWidget>& InWidget) const;
	
	
	
};
