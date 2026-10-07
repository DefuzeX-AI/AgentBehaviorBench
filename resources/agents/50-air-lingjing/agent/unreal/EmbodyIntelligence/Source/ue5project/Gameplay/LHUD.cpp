// Fill out your copyright notice in the Description page of Project Settings.

#include "LHUD.h"

#include "ue5project/Interaction/UserInterface/MainWidgetController.h"

ALHUD::ALHUD()
{
}

void ALHUD::BeginPlay()
{
	Super::BeginPlay();
	
	FMainWidgetController::Get()->CreateMainWidget();
}
