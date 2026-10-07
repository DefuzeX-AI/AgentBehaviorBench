// Fill out your copyright notice in the Description page of Project Settings.

#include "LGameMode.h"
#include "LPlayerController.h"
#include "LHUD.h"
#include "ue5project/Interaction/Scene/CameraController.h"

ALGameMode::ALGameMode()
{
	PlayerControllerClass = ALPlayerController::StaticClass();
	HUDClass = ALHUD::StaticClass();
}

void ALGameMode::BeginPlay()
{
	Super::BeginPlay();


	FCameraController::Get()->Init(GetWorld());
}
