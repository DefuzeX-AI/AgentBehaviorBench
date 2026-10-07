// Fill out your copyright notice in the Description page of Project Settings.


#include "MainWidgetController.h"

#include "SMainWidget.h"

FMainWidgetController* FMainWidgetController::Get()
{
	static FMainWidgetController Instance;
	return &Instance;
}

void FMainWidgetController::CreateMainWidget()
{
	RemoveMainWidget();
	
	SAssignNew(MainWidget, SMainWidget)
	.Visibility(EVisibility::SelfHitTestInvisible);
	GEngine->GameViewport->AddViewportWidgetContent(MainWidget.ToSharedRef());
}

void FMainWidgetController::RemoveMainWidget() const
{
	if (MainWidget.IsValid())
	{
		GEngine->GameViewport->RemoveViewportWidgetContent(MainWidget.ToSharedRef());
	}
}

TPanelChildren<SOverlay::FOverlaySlot>::FScopedWidgetSlotArguments FMainWidgetController::AddWidget() const
{
	return MainWidget->AddWidget();
}

void FMainWidgetController::AddWidget(const TSharedRef<SWidget>& InWidget) const
{
	if (MainWidget.IsValid())
	{
		MainWidget->AddWidget(InWidget);
	}
}

void FMainWidgetController::RemoveWidget(const TSharedRef<SWidget>& InWidget) const
{
	if (MainWidget.IsValid())
	{
		MainWidget->RemoveWidget(InWidget);
	}
}
