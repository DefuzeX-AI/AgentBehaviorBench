// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/HUD.h"
#include "LHUD.generated.h"

class SMainWidget;

UCLASS()
class UE5PROJECT_API ALHUD : public AHUD
{
	GENERATED_BODY()

public:
	ALHUD();

protected:
	virtual void BeginPlay() override;

};
